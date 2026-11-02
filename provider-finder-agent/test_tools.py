"""Quick test of the tools. Run:  python test_tools.py
No API key needed."""
from tools import *

print("1) Pediatrician near Issaquah, Premera, under 15 miles, female:")
for r in search_providers("Pediatrics", city="Issaquah", insurance="Premera", gender="female", max_miles=15):
    print("  ", r["name"], "-", r["city"], r["miles_away"], "mi, next:", r["next_available"])

print("\n1b) Sub-specialty search: sinus problems near Bellevue, Aetna PPO:")
for r in search_providers(focus="sinus", city="Bellevue", insurance="Aetna PPO", max_miles=20)[:3]:
    print("  ", r["name"], "-", r["specialty"], r["focus"], r["city"], "next:", r["next_available"])

print("\n1c) PCOS specialist near Seattle (any specialty):")
for r in search_providers(focus="PCOS", city="Seattle", max_miles=15)[:3]:
    print("  ", r["name"], "-", r["specialty"], r["focus"], r["city"], "next:", r["next_available"])

print("\n2) Not accepting new patients -> alternatives for Dr. Arjun Rao (p02):")
for r in find_alternatives("p02", insurance="Premera"):
    print("  ", r["name"], "-", r["city"], "next:", r["next_available"])

print("\n3) Availability before Oct 31 for Dr. Emily Carter (p03):")
print("  ", check_availability("p03", before_date="2026-10-31")["dates"])

print("\n4) Community mentions for Dr. Sofia Marino (p16):")
print("  ", get_community_mentions("p16")["posts"][0]["text"])

print("\n5) Draft a call script:")
print("  ", draft_contact("p16", "call", "a new-patient visit for my child")["draft"])
