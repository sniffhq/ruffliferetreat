"""
chat_service.py — AI chat backend using Groq API with tool/function calling.
Sniffr can query live database data to answer operational questions.
"""

import json
import logging
from datetime import date, datetime, timedelta
from flask import current_app

logger = logging.getLogger(__name__)

MODEL = 'llama-3.3-70b-versatile'

# ── System prompts ────────────────────────────────────────────────────────────

STAFF_SYSTEM = """You are Sniffr, a helpful AI assistant for staff at {business_name}, a pet boarding and daycare facility.
You have access to live facility data through tools — use them whenever a question involves numbers, schedules, or current status.
Be concise, friendly, and practical. Use the tools proactively — don't ask the user to look things up themselves.
When presenting data, ALWAYS include full details like names, amounts, and dates in your first response — never make the user ask a follow-up question to get the details.
When presenting lists, always show all names. Use bullet points for lists of pets or customers.
Always round dollar amounts to 2 decimal places.
For daycare schedule questions about tomorrow or a specific date, pass the actual date in YYYY-MM-DD format to get_daycare_today."""

CUSTOMER_SYSTEM = """You are Sniffr, a friendly support assistant for {business_name}, a pet boarding and daycare facility.
You can look up the customer's own reservations and account information using tools.
Be warm, helpful, and reassuring. Keep answers brief and easy to understand.
If you don't know the answer, suggest the customer contact {business_phone}."""

# ── Tool definitions ──────────────────────────────────────────────────────────

STAFF_TOOLS = [
    {"type":"function","function":{"name":"get_boarding_today","description":"Get all pets currently checked in for boarding today.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_upcoming_boardings","description":"Get upcoming boarding reservations for the next N days.","parameters":{"type":"object","properties":{"days":{"description":"Number of days ahead to look. Default 7."}},"required":[]}}},
    {"type":"function","function":{"name":"get_daycare_today","description":"Get pets in daycare or scheduled for daycare on a given date. Pass date as YYYY-MM-DD, defaults to today.","parameters":{"type":"object","properties":{"date":{"type":"string","description":"Date in YYYY-MM-DD format. Defaults to today."}},"required":[]}}},
    {"type":"function","function":{"name":"get_busiest_day","description":"Find the busiest day of the week for boarding or daycare based on historical data.","parameters":{"type":"object","properties":{"service":{"type":"string","enum":["boarding","daycare"],"description":"Service type to analyze."}},"required":["service"]}}},
    {"type":"function","function":{"name":"get_outstanding_balances","description":"Get total outstanding balances and list of customers who owe money.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_occupancy","description":"Get current boarding occupancy — how many kennels are occupied vs total capacity.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_revenue_summary","description":"Get revenue summary for a given period.","parameters":{"type":"object","properties":{"period":{"type":"string","enum":["today","this_week","this_month","last_month"],"description":"Time period."}},"required":["period"]}}},
    {"type":"function","function":{"name":"get_expiring_vaccinations","description":"Get pets with vaccinations expiring soon.","parameters":{"type":"object","properties":{"days":{"description":"Number of days ahead to check. Default 30."}},"required":[]}}},
    {"type":"function","function":{"name":"get_customer_count","description":"Get total number of active customers and new customers this month.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_kb_article","description":"Search the knowledge base for articles relevant to a topic.","parameters":{"type":"object","properties":{"query":{"type":"string","description":"Search query."}},"required":["query"]}}},
]

CUSTOMER_TOOLS = [
    {"type":"function","function":{"name":"get_my_upcoming_reservations","description":"Get the customer's upcoming boarding reservations.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_my_balance","description":"Get the customer's current outstanding balance.","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"get_my_pets","description":"Get the customer's registered pets and their vaccination status.","parameters":{"type":"object","properties":{},"required":[]}}},
]

# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    try:
        from groq import Groq
        api_key = current_app.config.get('GROQ_API_KEY', '')
        if not api_key:
            raise ValueError('GROQ_API_KEY not configured')
        return Groq(api_key=api_key)
    except ImportError:
        raise RuntimeError('groq package not installed. Run: pip install groq')

# ── Tool runner ───────────────────────────────────────────────────────────────

def _run_with_tools(client, messages, tools, tool_executor, system_prompt=''):
    MAX_TOOL_ROUNDS = 5
    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL, messages=messages, tools=tools,
            tool_choice='auto', max_tokens=1024, temperature=0.3,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            return msg.content
        messages.append({
            'role': 'assistant', 'content': msg.content or '',
            'tool_calls': [{'id': tc.id, 'type': 'function',
                'function': {'name': tc.function.name, 'arguments': tc.function.arguments}}
                for tc in msg.tool_calls]
        })
        for tc in msg.tool_calls:
            try:
                args   = json.loads(tc.function.arguments or '{}')
                result = tool_executor(tc.function.name, args)
                logger.info(f'Tool {tc.function.name} => {str(result)[:150]}')
            except Exception as e:
                import traceback
                logger.error(f'Tool {tc.function.name} FAILED: {e}\n{traceback.format_exc()}')
                result = f'Tool error: {e}'
            messages.append({'role': 'tool', 'tool_call_id': tc.id, 'content': result})
    return "I wasn't able to complete that request. Please try rephrasing."

# ── Staff tool executor ───────────────────────────────────────────────────────

def _execute_staff_tool(name, args):
    from app.models import (Boarding, DaycareAttendance, DaycareEnrollment,
                             User, Pet, VaccinationRecord, Payment, KnowledgeArticle)
    from datetime import date, datetime, timedelta
    today = date.today()

    if name == 'get_boarding_today':
        boardings = Boarding.query.filter(
            Boarding.check_in_date <= today, Boarding.check_out_date >= today,
            Boarding.status == 'active', Boarding.checked_in == True
        ).all()
        if not boardings:
            return "No pets are currently checked in for boarding today."
        lines = [f"**{len(boardings)} pet(s) checked in today:**"]
        for b in boardings:
            owner = User.query.get(b.user_id)
            pet   = Pet.query.get(b.pet_id)
            lines.append(f"• {pet.name if pet else '?'} ({pet.breed or 'Unknown' if pet else ''}) — "
                        f"owner: {owner.first_name} {owner.last_name if owner else '?'}, "
                        f"checking out {b.check_out_date.strftime('%b %d')}")
        return '\n'.join(lines)

    elif name == 'get_upcoming_boardings':
        days = int(args.get('days', 7))
        end  = today + timedelta(days=days)
        upcoming = Boarding.query.filter(
            Boarding.check_in_date > today, Boarding.check_in_date <= end,
            Boarding.status == 'active'
        ).order_by(Boarding.check_in_date.asc()).all()
        if not upcoming:
            return f"No upcoming boardings in the next {days} days."
        lines = [f"**{len(upcoming)} upcoming boarding(s) in the next {days} days:**"]
        for b in upcoming:
            owner = User.query.get(b.user_id)
            pet   = Pet.query.get(b.pet_id)
            lines.append(f"• {pet.name if pet else '?'} — "
                        f"{b.check_in_date.strftime('%b %d')} to {b.check_out_date.strftime('%b %d')} "
                        f"({owner.first_name} {owner.last_name if owner else '?'})")
        return '\n'.join(lines)

    elif name == 'get_daycare_today':
        target_date = today
        if args.get('date'):
            try:
                target_date = datetime.strptime(args['date'], '%Y-%m-%d').date()
            except Exception:
                pass
        day_of_week = target_date.weekday()
        day_names   = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        label       = 'today' if target_date == today else target_date.strftime('%A, %b %d')

        # Check actual attendance
        attendances = DaycareAttendance.query.filter(
            DaycareAttendance.check_in_time >= datetime.combine(target_date, datetime.min.time()),
            DaycareAttendance.check_in_time <  datetime.combine(target_date + timedelta(days=1), datetime.min.time()),
        ).all()
        if attendances:
            lines = [f"**{len(attendances)} pet(s) in daycare on {label}:**"]
            for a in attendances:
                enr   = DaycareEnrollment.query.get(a.enrollment_id)
                pet   = Pet.query.get(enr.pet_id) if enr else None
                owner = User.query.get(pet.user_id) if pet else None
                status = 'checked out' if a.check_out_time else 'checked in'
                lines.append(f"• {pet.name if pet else 'Unknown'} ({status})"
                            + (f" — {owner.first_name} {owner.last_name}" if owner else ""))
            return '\n'.join(lines)

        # Fall back to enrollment schedule
        day_col_map = {0:'monday',1:'tuesday',2:'wednesday',3:'thursday',4:'friday',5:'saturday',6:'sunday'}
        day_col     = day_col_map.get(day_of_week)
        if day_col:
            enrollments = DaycareEnrollment.query.filter(
                getattr(DaycareEnrollment, day_col) == True,
                DaycareEnrollment.active == True
            ).all()
        else:
            enrollments = []
        if not enrollments:
            return f"No daycare pets scheduled for {label} ({day_names[day_of_week]})."
        lines = [f"**{len(enrollments)} pet(s) scheduled for daycare on {label}:**"]
        for enr in enrollments:
            pet   = Pet.query.get(enr.pet_id)
            owner = User.query.get(pet.user_id) if pet else None
            rate  = f"${enr.special_rate:.0f}/day" if enr.special_rate else "standard rate"
            lines.append(f"• {pet.name if pet else 'Unknown'} ({rate})"
                        + (f" — {owner.first_name} {owner.last_name}" if owner else ""))
        return '\n'.join(lines)

    elif name == 'get_busiest_day':
        service   = args.get('service', 'boarding')
        day_names = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
        counts    = {i: 0 for i in range(7)}
        if service == 'boarding':
            for b in Boarding.query.filter(Boarding.status.in_(['active','completed'])).all():
                counts[b.check_in_date.weekday()] += 1
        else:
            for a in DaycareAttendance.query.all():
                counts[a.check_in_time.weekday()] += 1
        if not any(counts.values()):
            return f"Not enough {service} data yet."
        sorted_days = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        lines = [f"**{service.capitalize()} by day of week:**"]
        for day_idx, count in sorted_days:
            bar = '█' * min(count, 20)
            lines.append(f"• {day_names[day_idx]}: {count} {bar}")
        return '\n'.join(lines) + f"\n\n**Busiest day: {day_names[sorted_days[0][0]]}**"

    elif name == 'get_outstanding_balances':
        customers = User.query.filter_by(role='customer', is_active=True).all()
        total = 0.0
        owing = []
        for c in customers:
            balance = 0.0
            for pet in c.pets:
                unpaid = Boarding.query.filter_by(
                    pet_id=pet.id, status='completed'
                ).filter(Boarding.payment_id == None).all()
                for b in unpaid:
                    days = max((b.check_out_date - b.check_in_date).days, 1)
                    balance += days * 40.0
                unpaid_dc = DaycareAttendance.query.join(DaycareEnrollment).filter(
                    DaycareEnrollment.pet_id == pet.id,
                    DaycareAttendance.check_out_time != None,
                    DaycareAttendance.payment_id == None
                ).all()
                balance += len(unpaid_dc) * 22.0
            if balance > 0:
                owing.append((c, balance))
                total += balance
        if not owing:
            return "No outstanding balances — all accounts are current! 🎉"
        owing.sort(key=lambda x: x[1], reverse=True)
        lines = [f"**Total outstanding: ${total:.2f} across {len(owing)} customer(s):**"]
        for customer, bal in owing:
            lines.append(f"• {customer.first_name} {customer.last_name}: ${bal:.2f}")
        return '\n'.join(lines)

    elif name == 'get_occupancy':
        capacity   = current_app.config.get('KENNEL_CAPACITY', 20)
        checked_in = Boarding.query.filter(
            Boarding.check_in_date <= today, Boarding.check_out_date >= today,
            Boarding.status == 'active', Boarding.checked_in == True
        ).count()
        pct = int((checked_in / capacity) * 100) if capacity else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        return (f"**Current occupancy: {checked_in}/{capacity} kennels ({pct}%)**\n"
                f"[{bar}]\n{'⚠️ Nearly full!' if pct >= 80 else '✓ Space available'}")

    elif name == 'get_revenue_summary':
        period = args.get('period', 'this_month')
        if period == 'today':
            start, label = today, 'Today'
        elif period == 'this_week':
            start, label = today - timedelta(days=today.weekday()), 'This week'
        elif period == 'this_month':
            start, label = today.replace(day=1), 'This month'
        else:
            last  = (today.replace(day=1) - timedelta(days=1))
            start = last.replace(day=1)
            label = last.strftime('%B %Y')
        payments = Payment.query.filter(Payment.payment_date >= start, Payment.status == 'paid').all()
        total    = sum(p.amount for p in payments)
        boarding = sum(p.amount for p in payments if p.service_type == 'Boarding')
        daycare  = sum(p.amount for p in payments if p.service_type == 'Daycare')
        return (f"**{label} revenue: ${total:.2f}**\n• Boarding: ${boarding:.2f}\n"
                f"• Daycare: ${daycare:.2f}\n• Payments: {len(payments)}")

    elif name == 'get_expiring_vaccinations':
        days = int(args.get('days', 30))
        end  = today + timedelta(days=days)
        records = VaccinationRecord.query.filter(
            VaccinationRecord.expiration_date >= today,
            VaccinationRecord.expiration_date <= end
        ).all()
        if not records:
            return f"No vaccinations expiring in the next {days} days."
        lines = [f"**{len(records)} vaccination(s) expiring in the next {days} days:**"]
        for r in sorted(records, key=lambda x: x.expiration_date):
            pet   = Pet.query.get(r.pet_id)
            owner = User.query.get(pet.user_id) if pet else None
            days_left = (r.expiration_date - today).days
            lines.append(f"• {pet.name if pet else '?'} — {r.vaccine_name} expires "
                        f"{r.expiration_date.strftime('%b %d')} ({days_left}d)"
                        + (f" — {owner.first_name} {owner.last_name}" if owner else ""))
        return '\n'.join(lines)

    elif name == 'get_customer_count':
        total      = User.query.filter_by(role='customer', is_active=True).count()
        new_this   = User.query.filter(User.role == 'customer',
                                        User.created_at >= today.replace(day=1)).count()
        return (f"**Customer overview:**\n• Total active: {total}\n• New this month: {new_this}")

    elif name == 'get_kb_article':
        query    = args.get('query', '')
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        articles = KnowledgeArticle.query.all()
        scored   = []
        for a in articles:
            score = sum(2 if kw in a.title.lower() else 1
                       for kw in keywords if kw in (a.title + a.content).lower())
            if score > 0:
                scored.append((score, a))
        scored.sort(key=lambda x: x[0], reverse=True)
        if not scored:
            return "No relevant KB articles found."
        return '\n\n---\n\n'.join(
            f"**{a.title}** ({a.category})\n{a.content[:600]}"
            for _, a in scored[:2]
        )

    return f"Unknown tool: {name}"

# ── Customer tool executor ────────────────────────────────────────────────────

def _execute_customer_tool(name, args, user_id):
    from app.models import Boarding, DaycareAttendance, DaycareEnrollment, Pet, VaccinationRecord
    today = date.today()

    if name == 'get_my_upcoming_reservations':
        pets    = Pet.query.filter_by(user_id=user_id, is_active=True).all()
        pet_ids = [p.id for p in pets]
        upcoming = Boarding.query.filter(
            Boarding.pet_id.in_(pet_ids),
            Boarding.check_out_date >= today,
            Boarding.status == 'active'
        ).order_by(Boarding.check_in_date.asc()).all()
        if not upcoming:
            return "You don't have any upcoming boarding reservations."
        lines = ["**Your upcoming reservation(s):**"]
        for b in upcoming:
            pet    = Pet.query.get(b.pet_id)
            status = "Currently checked in" if b.checked_in else "Upcoming"
            lines.append(f"• {pet.name}: {b.check_in_date.strftime('%b %d')} → "
                        f"{b.check_out_date.strftime('%b %d')} ({status})")
        return '\n'.join(lines)

    elif name == 'get_my_balance':
        pets  = Pet.query.filter_by(user_id=user_id, is_active=True).all()
        total = sum(
            Boarding.query.filter_by(pet_id=p.id, status='completed')
                .filter(Boarding.payment_id == None).count() * 40.0
            for p in pets
        )
        if total == 0:
            return "Your account balance is $0.00 — you're all paid up! ✓"
        return f"Your current outstanding balance is approximately **${total:.2f}**. Please contact us to arrange payment."

    elif name == 'get_my_pets':
        pets = Pet.query.filter_by(user_id=user_id, is_active=True).all()
        if not pets:
            return "You don't have any pets registered yet."
        lines = ["**Your registered pets:**"]
        for pet in pets:
            records = VaccinationRecord.query.filter_by(pet_id=pet.id).all()
            valid   = [r for r in records if r.expiration_date and r.expiration_date >= today]
            vacc    = ("✓ Vaccinations current" if valid else
                      ("⚠️ Vaccinations expired" if records else "❌ No vaccination records"))
            lines.append(f"• **{pet.name}** ({pet.breed or 'Mixed'}, {pet.age}yr) — {vacc}")
        return '\n'.join(lines)

    return f"Unknown tool: {name}"

# ── FAQ context ───────────────────────────────────────────────────────────────

def _get_faq_context():
    business = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
    phone    = current_app.config.get('BUSINESS_PHONE', '')
    address  = current_app.config.get('BUSINESS_ADDRESS', '')
    domain   = current_app.config.get('BUSINESS_DOMAIN', '')
    return f"""FAQ for {business}
Address: {address} | Phone: {phone} | Website: {domain}
Boarding: Check-in 7-10 AM, Check-out 3-6 PM (Sunday by 3 PM). $40/night first pet, $25 additional.
Daycare: $25/day single day, $20/day multi-day. Drop-off 7 AM, pick-up by 6 PM.
Grooming add-ons: Spa Bath + Nails $20, Bath only $15, Nails only $10.
Vaccinations required: Rabies, DHPP, Bordetella. Payment: Cash or Zelle only."""

# ── Public chat functions ─────────────────────────────────────────────────────

def chat_staff(message, history=None):
    client   = _get_groq_client()
    business = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
    system   = STAFF_SYSTEM.format(business_name=business)
    messages = [{'role': 'system', 'content': system}]
    if history:
        for turn in history[-8:]:
            messages.append({'role': turn['role'], 'content': turn['content']})
    messages.append({'role': 'user', 'content': message})
    return _run_with_tools(client, messages, STAFF_TOOLS, _execute_staff_tool, system_prompt=system)


def chat_customer(message, history=None, user_id=None):
    client   = _get_groq_client()
    business = current_app.config.get('BUSINESS_NAME', 'Ruff Life Retreat')
    phone    = current_app.config.get('BUSINESS_PHONE', '')
    system   = CUSTOMER_SYSTEM.format(business_name=business, business_phone=phone)
    system  += f'\n\nFACILITY INFORMATION:\n{_get_faq_context()}'
    messages = [{'role': 'system', 'content': system}]
    if history:
        for turn in history[-8:]:
            messages.append({'role': turn['role'], 'content': turn['content']})
    messages.append({'role': 'user', 'content': message})

    def customer_tool_executor(name, args):
        return _execute_customer_tool(name, args, user_id)

    return _run_with_tools(client, messages, CUSTOMER_TOOLS, customer_tool_executor, system_prompt=system)