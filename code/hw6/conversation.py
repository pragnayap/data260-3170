"""
The fixed 30-message conversation used by every Part 3 run.

Messages 1-6 plant the five facts the probes ask about (memory_probes.yaml).
Messages 7-30 are realistic transit-incident chatter that neither repeats nor
contradicts those facts, so by turn 31 an N=4 window has lost all of them.
"""

CONVERSATION = [
    # --- planted facts ---------------------------------------------------
    "Hi, I'm Lucky, a grad student at SJSU, and I want to report a few transit problems.",
    "I ride the Line 22 bus every weekday morning, boarding at Downtown Transit Center around 7:15.",
    "I always bring my folding bike, so I need buses that have a working bike rack.",
    "For follow-ups please email me at lucky.rider@example.com, I don't want text messages.",
    "Last week the elevators at Civic Center Station on the BART Red Line were out of service all morning.",
    "That outage made me miss my connection, so it counts as a mechanical failure, right?",
    # --- filler: incident chatter ----------------------------------------
    "How long does the transit agency usually take to answer an incident report?",
    "What details should a good incident description include?",
    "Is a bus that arrives twenty minutes late classified as a delay or something else?",
    "What is the difference between a safety hazard and a mechanical failure?",
    "Yesterday a bus door would not close for several minutes at a busy stop. Which category is that?",
    "Should I report it if the driver was polite but the bus was overcrowded?",
    "Can I attach a photo to an incident report?",
    "What happens to a report after it is marked Investigating?",
    "How are accident and collision reports handled differently from delays?",
    "If two riders report the same incident, are the reports merged?",
    "Is there a time limit for reporting something that happened last month?",
    "What should I do if I see a spill on the platform floor?",
    "Do reports about bus stops without shelters count as safety hazards?",
    "How can I tell whether a report I filed has been resolved?",
    "Are the incident categories the same for light rail and buses?",
    "What information do dispatchers see when I submit a report?",
    "If a route is cancelled for the day, is that a delay or a separate category?",
    "Can a rider report an incident on behalf of someone else?",
    "How are repeated incidents on the same route tracked over time?",
    "Does the agency publish statistics about how many incidents are resolved each month?",
    "What is a reasonable response time for a safety hazard compared with a delay?",
    "If I disagree with how my report was categorized, how do I appeal?",
    "Is it better to report several small problems together or one at a time?",
    "Thanks, that covers it. Is there anything else I should know before filing my reports?",
]

assert len(CONVERSATION) == 30
