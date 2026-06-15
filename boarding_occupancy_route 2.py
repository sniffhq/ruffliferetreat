
@bp.route('/reports/boarding-occupancy')
@login_required
@admin_required
def boarding_occupancy_report():
    """Daily boarding drop-off and pickup report with kennel assignments."""
    from app.models import Boarding, Pet
    from datetime import date, timedelta

    today = date.today()

    # Date range — default to current week (Mon–Sun) or use query params
    try:
        start_date = date.fromisoformat(request.args.get('start', ''))
    except (ValueError, TypeError):
        start_date = today - timedelta(days=today.weekday())  # Monday

    try:
        end_date = date.fromisoformat(request.args.get('end', ''))
    except (ValueError, TypeError):
        end_date = start_date + timedelta(days=13)  # 2 weeks

    # Clamp range to max 60 days
    if (end_date - start_date).days > 60:
        end_date = start_date + timedelta(days=59)

    # Pull all boardings that overlap the date range
    boardings = Boarding.query.filter(
        Boarding.status.in_(['active', 'completed']),
        Boarding.check_in_date  <= end_date,
        Boarding.check_out_date >= start_date,
    ).order_by(Boarding.check_in_date, Boarding.check_in_time).all()

    # Build day-by-day structure
    days = []
    d = start_date
    while d <= end_date:
        dropoffs = []
        pickups  = []
        staying  = []

        for b in boardings:
            owner = b.pet.owner if b.pet else None
            entry = {
                'id':           b.id,
                'pet_name':     b.pet.name if b.pet else '—',
                'pet_breed':    b.pet.breed or '' if b.pet else '',
                'owner_name':   f'{owner.first_name} {owner.last_name}' if owner else '—',
                'owner_phone':  owner.phone or '—' if owner else '—',
                'check_in_time':  b.check_in_time  or '—',
                'check_out_time': b.check_out_time or '—',
                'kennel_type':  (b.kennel_type or 'kennel').title(),
                'kennel_number': b.kennel_number or '—',
                'kennel_label': f'{(b.kennel_type or "Kennel").title()} #{b.kennel_number}' if b.kennel_number else 'Unassigned',
                'status':       b.status,
                'nights':       (b.check_out_date - b.check_in_date).days,
            }
            if b.check_in_date == d:
                dropoffs.append(entry)
            elif b.check_out_date == d:
                pickups.append(entry)
            elif b.check_in_date < d < b.check_out_date:
                staying.append(entry)

        # Sort by time
        def sort_time(e):
            t = e['check_in_time'] if e in dropoffs else e['check_out_time']
            return t if t and t != '—' else '99:99'

        dropoffs.sort(key=lambda e: e['check_in_time']  or '99:99')
        pickups.sort( key=lambda e: e['check_out_time'] or '99:99')
        staying.sort( key=lambda e: e['kennel_label'])

        days.append({
            'date':         d,
            'is_today':     d == today,
            'is_past':      d < today,
            'dropoffs':     dropoffs,
            'pickups':      pickups,
            'staying':      staying,
            'total_guests': len(dropoffs) + len(staying),
        })
        d += timedelta(days=1)

    # Navigation — prev/next 2-week windows
    prev_start = start_date - timedelta(days=14)
    next_start = start_date + timedelta(days=14)

    return render_template('admin/boarding_occupancy.html',
        days=days,
        start_date=start_date,
        end_date=end_date,
        prev_start=prev_start,
        next_start=next_start,
        today=today,
    )
