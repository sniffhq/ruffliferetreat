# cleanup_fake_waitlist.py
# Run this from the RuffLifeRetreat directory: python cleanup_fake_waitlist.py
# 
# This script identifies and removes fake bot entries from the daycare waitlist

import sys
import os
import re

# Add the app to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import DaycareWaitlist

app = create_app()

def is_gibberish_name(name):
    """Check if a name looks like bot-generated gibberish"""
    if not name:
        return False
    name = name.lower().strip()
    
    # Pattern: 4+ consonants in a row
    consonant_cluster = re.compile(r'[bcdfghjklmnpqrstvwxyz]{4,}')
    if consonant_cluster.search(name):
        return True
    
    # If name has no vowels and is longer than 3 chars
    vowel_count = sum(1 for c in name if c in 'aeiou')
    if len(name) > 3 and vowel_count == 0:
        return True
    
    # Ratio check: if less than 20% vowels in a name 6+ chars, likely gibberish
    if len(name) >= 6 and (vowel_count / len(name)) < 0.2:
        return True
    
    return False


def main():
    with app.app_context():
        print("=" * 70)
        print("RUFF LIFE RETREAT - DAYCARE WAITLIST CLEANUP")
        print("=" * 70)
        print()
        
        # Get all waitlist entries
        total_entries = DaycareWaitlist.query.count()
        print(f"Total waitlist entries: {total_entries}")
        print()
        
        # Find fake entries
        all_entries = DaycareWaitlist.query.all()
        fake_entries = []
        
        for entry in all_entries:
            first_gibberish = is_gibberish_name(entry.first_name)
            last_gibberish = is_gibberish_name(entry.last_name)
            
            # Flag if either name is gibberish
            if first_gibberish or last_gibberish:
                fake_entries.append(entry)
        
        if not fake_entries:
            print("No fake entries detected based on gibberish names!")
            return
        
        print(f"Found {len(fake_entries)} suspected fake entries")
        print()
        
        # Show sample of fake entries
        print("Sample of fake entries (first 10):")
        print("-" * 70)
        print(f"{'#':<4} {'Name':<30} {'Email':<35}")
        print("-" * 70)
        
        for i, entry in enumerate(fake_entries[:10], 1):
            name = f"{entry.first_name} {entry.last_name}"[:28]
            email = str(entry.email)[:33]
            print(f"{i:<4} {name:<30} {email:<35}")
        
        if len(fake_entries) > 10:
            print(f"... and {len(fake_entries) - 10} more")
        
        print("-" * 70)
        print()
        print("Options:")
        print(f"  all   - Delete ALL {len(fake_entries)} fake entries")
        print("  no    - Cancel and exit")
        print()
        
        choice = input("Enter your choice: ").strip().lower()
        
        if choice != 'all':
            print("\nOperation cancelled. No entries were deleted.")
            return
        
        # Confirm deletion
        print(f"\nAbout to delete {len(fake_entries)} fake waitlist entries.")
        confirm = input("Type 'DELETE' to confirm: ").strip()
        
        if confirm == 'DELETE':
            # Get IDs to delete
            fake_ids = [entry.id for entry in fake_entries]
            
            # Bulk delete
            deleted = DaycareWaitlist.query.filter(DaycareWaitlist.id.in_(fake_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            print(f"\n✓ Successfully deleted {deleted} fake waitlist entries.")
            
            # Show remaining count
            remaining = DaycareWaitlist.query.count()
            print(f"Remaining legitimate entries: {remaining}")
        else:
            print("\nOperation cancelled. No entries were deleted.")


if __name__ == '__main__':
    main()