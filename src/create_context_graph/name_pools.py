# Copyright 2026 Neo4j Labs
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Realistic name pools and value generators for static fixture data.

Provides domain-appropriate names and property values so that the static
fallback generator produces passable demo data without an LLM.
"""

from __future__ import annotations

import random
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Name pools organized by POLE+O type
# ---------------------------------------------------------------------------

PERSON_NAMES = [
    "Sarah Chen", "James Morrison", "Maria Rodriguez", "David Park",
    "Elena Volkov", "Michael O'Brien", "Aisha Patel", "Robert Kim",
    "Lisa Nakamura", "Carlos Gutierrez", "Fatima Al-Hassan", "Thomas Weber",
    "Priya Sharma", "John Washington", "Yuki Tanaka", "Rachel Okonkwo",
    "Andreas Mueller", "Sofia Petrova", "Benjamin Adeyemi", "Grace Nguyen",
    "Marcus Thompson", "Isabelle Fournier", "Omar Rashid", "Emily Hartman",
    "Daniel Kowalski",
]

ORGANIZATION_NAMES = [
    "Meridian Consulting Group", "Pacific Northwest Industries",
    "Apex Financial Partners", "Greenleaf Technologies",
    "Summit Healthcare Systems", "Atlas Data Solutions",
    "Cornerstone Engineering", "BlueStar Analytics",
    "Ironwood Manufacturing", "Catalyst Research Labs",
    "Nexus Global Services", "Harbourview Capital",
    "Pinnacle Logistics", "Quantum Dynamics Corp",
    "Redwood Environmental", "Sterling Associates",
    "Trident Marine Solutions", "Vanguard Innovations",
    "Westfield Properties", "Zenith Aerospace",
]

LOCATION_NAMES = [
    "Downtown Medical Center", "Westside Corporate Campus",
    "Harbor View Complex", "Mountain Ridge Facility",
    "Riverside Research Park", "Lakefront Office Tower",
    "Northern District Hub", "Central Processing Center",
    "Coastal Operations Base", "Metropolitan Data Center",
    "Valley Industrial Park", "Skyline Business Center",
    "Oakwood Conference Center", "Bayshore Distribution Hub",
    "Parkside Innovation Lab",
]

EVENT_NAMES = [
    "Q4 Strategy Review", "Annual Compliance Audit",
    "Emergency Response Drill", "Product Launch Summit",
    "Board of Directors Meeting", "Technology Integration Workshop",
    "Quarterly Performance Review", "Safety Inspection Round",
    "Customer Advisory Council", "Research Symposium",
    "Budget Planning Session", "Stakeholder Town Hall",
]

OBJECT_NAMES = [
    "Primary Analysis Report", "Standard Operating Procedure",
    "Quarterly Assessment Document", "Technical Specification",
    "Compliance Certificate", "Risk Evaluation Matrix",
    "Performance Dashboard", "Quality Control Record",
    "Strategic Initiative Brief", "Operations Manual",
    "Incident Response Protocol", "Resource Allocation Plan",
]

# ---------------------------------------------------------------------------
# Domain-specific label name pools — override POLE+O pools for known labels
# ---------------------------------------------------------------------------

LABEL_NAMES: dict[str, list[str]] = {
    # Healthcare
    "Patient": [
        "James Morrison", "Maria Rodriguez", "David Park", "Aisha Patel",
        "Carlos Gutierrez", "Lisa Nakamura", "Thomas Weber", "Grace Nguyen",
        "Ahmed Hassan", "Emily Hartman", "Robert Kim", "Priya Sharma",
    ],
    "Provider": [
        "Dr. Sarah Chen", "Dr. Michael O'Brien", "Dr. Elena Volkov",
        "Dr. Yuki Tanaka", "Dr. Rachel Okonkwo", "Dr. Andreas Mueller",
        "Dr. Sofia Petrova", "Dr. Benjamin Adeyemi",
    ],
    "Diagnosis": [
        "Type 2 Diabetes Mellitus", "Essential Hypertension",
        "Acute Myocardial Infarction", "Major Depressive Disorder",
        "Chronic Obstructive Pulmonary Disease", "Atrial Fibrillation",
        "Rheumatoid Arthritis", "Asthma", "Chronic Kidney Disease Stage 3",
        "Iron Deficiency Anemia", "Generalized Anxiety Disorder",
        "Osteoporosis",
    ],
    "Medication": [
        "Metformin 500mg", "Lisinopril 10mg", "Atorvastatin 40mg",
        "Amoxicillin 250mg", "Sertraline 50mg", "Metoprolol 25mg",
        "Omeprazole 20mg", "Levothyroxine 50mcg", "Amlodipine 5mg",
        "Prednisone 10mg",
    ],
    "Treatment": [
        "Cardiac Catheterization", "Physical Therapy Program",
        "Cognitive Behavioral Therapy", "Chemotherapy Cycle 1",
        "Joint Replacement Surgery", "Dialysis Treatment",
        "Radiation Therapy", "Pulmonary Rehabilitation",
    ],
    "Encounter": [
        "Annual Physical Exam", "Emergency Room Visit",
        "Follow-Up Appointment", "Surgical Consultation",
        "Lab Work Review", "Telehealth Visit",
    ],
    "Facility": [
        "Memorial General Hospital", "Riverside Medical Center",
        "St. Mary's Regional Hospital", "University Health System",
        "Cedar Grove Clinic", "Pacific Northwest Medical",
    ],
    # Financial Services
    "Account": [
        "Premium Checking - 4821", "Retirement IRA - 7293",
        "Business Savings - 5618", "High-Yield Money Market - 3047",
        "Joint Checking - 8156", "Trust Fund - 2394",
        "Corporate Treasury - 6712", "Student Savings - 1985",
    ],
    "Transaction": [
        "Wire Transfer #TXN-2025-0142", "ACH Payment #TXN-2025-0287",
        "Stock Purchase #TXN-2025-0351", "Dividend Payout #TXN-2025-0419",
        "Loan Disbursement #TXN-2025-0508", "Currency Exchange #TXN-2025-0623",
        "Bond Redemption #TXN-2025-0741", "Fee Assessment #TXN-2025-0855",
    ],
    "Security": [
        "Apple Inc (AAPL)", "US Treasury 10Y Bond", "Vanguard S&P 500 ETF (VOO)",
        "Microsoft Corp (MSFT)", "Amazon.com Inc (AMZN)",
        "Municipal Bond Fund AAA", "Gold Futures Dec 2025",
        "Tesla Inc (TSLA)",
    ],
    "Policy": [
        "Anti-Money Laundering Policy", "Know Your Customer Guidelines",
        "Credit Risk Management Framework", "Trading Compliance Manual",
        "Data Privacy Standards", "Conflict of Interest Policy",
    ],
    "Decision": [
        "Loan Approval Q4-2025", "Portfolio Rebalance Dec-2025",
        "Risk Assessment Client-847", "Compliance Review Case-192",
        "Investment Committee Vote Jan-2026", "Credit Line Extension Review",
    ],
    # Software Engineering
    "Repository": [
        "auth-service", "frontend-dashboard", "api-gateway",
        "data-pipeline", "notification-engine", "user-management",
        "payment-processor", "analytics-platform",
    ],
    "Issue": [
        "Memory leak in worker pool", "OAuth2 token refresh fails silently",
        "Dashboard shows stale data", "Rate limiter too aggressive",
        "Search results not paginated", "Mobile layout broken on tablets",
        "Batch job timeout at 10K records", "CORS headers missing on /api/v2",
    ],
    "PullRequest": [
        "Fix OAuth2 token refresh", "Add rate limiting middleware",
        "Migrate to PostgreSQL 16", "Implement WebSocket notifications",
        "Add Prometheus metrics", "Refactor user service to DDD",
        "Enable gzip compression", "Add OpenTelemetry tracing",
    ],
    "Deployment": [
        "Production v2.4.1", "Staging v2.5.0-rc1",
        "Canary deploy auth-service", "Hotfix v2.4.2",
        "Blue/Green switch v3.0.0", "Rollback v2.3.9",
    ],
    "Service": [
        "user-api", "payment-gateway", "notification-service",
        "search-indexer", "cdn-proxy", "auth-provider",
    ],
    "Incident": [
        "INC-2025-041 Database failover", "INC-2025-078 API latency spike",
        "INC-2025-112 Certificate expiry", "INC-2025-156 DDoS mitigation",
        "INC-2025-189 Data corruption", "INC-2025-201 Region outage",
    ],
    # Gaming
    "Player": [
        "ShadowKnight_42", "CrystalMage99", "IronWolf_X",
        "StarFire_Legend", "ThunderBlade77", "MysticArcher_V",
        "DragonSlayer_88", "FrostQueen_12",
    ],
    "Character": [
        "Kael the Shadowblade", "Lyra Starweaver", "Thane Ironjaw",
        "Zara the Enchantress", "Grimm Darkhollow", "Aria Lightbringer",
        "Rex Stormfist", "Nyx the Silent",
    ],
    "Item": [
        "Sword of Eternal Flame", "Shield of the Ancient Guardian",
        "Amulet of Whispered Secrets", "Boots of Swift Shadow",
        "Staff of Arcane Mastery", "Ring of Undying Resolve",
        "Cloak of Invisibility", "Helm of the Dragon King",
    ],
    "Quest": [
        "The Dragon's Lair", "Lost Temple of Shadows",
        "The Merchant's Dilemma", "Siege of the Crystal Fortress",
        "The Cursed Forest Path", "Rescue the King's Heir",
    ],
    "Guild": [
        "Order of the Silver Dawn", "The Crimson Brotherhood",
        "Shadow Covenant", "Ironforge Alliance",
        "Celestial Guardians", "The Wild Hunt",
    ],
    "Achievement": [
        "Dragon Slayer", "Master Explorer", "First Blood",
        "Legendary Crafter", "Undefeated Champion", "Treasure Hunter",
    ],
    # Trip Planning
    "Destination": [
        "Paris, France", "Tokyo, Japan", "Barcelona, Spain",
        "Bali, Indonesia", "Reykjavik, Iceland", "Cape Town, South Africa",
        "Machu Picchu, Peru", "Kyoto, Japan",
    ],
    "Hotel": [
        "Grand Hyatt Riverview", "Boutique Hotel du Marais",
        "Seaside Resort & Spa", "Mountain Lodge Retreat",
        "Metropolitan Tower Hotel", "Historic Inn at the Harbor",
    ],
    "Activity": [
        "Guided Walking Tour", "Sunset Kayak Adventure",
        "Cooking Class with Local Chef", "Wine Tasting Experience",
        "Scenic Helicopter Tour", "Snorkeling Expedition",
        "Historical Museum Visit", "Mountain Hiking Trail",
    ],
    "Restaurant": [
        "Le Petit Bistro", "Sakura Sushi Bar", "Trattoria del Porto",
        "The Rooftop Garden", "Casa de Tapas", "Café des Artistes",
    ],
    "Itinerary": [
        "European Summer 2025", "Southeast Asia Backpacking",
        "Mediterranean Cruise Week", "Japan Cherry Blossom Tour",
        "African Safari Adventure", "Nordic Winter Escape",
    ],
    "Review": [
        "5-Star Beach Resort Review", "Budget Hostel Feedback",
        "Restaurant Dining Experience", "Tour Guide Rating",
    ],
    # Real Estate
    "Property": [
        "123 Oak Lane Colonial", "456 Marina Drive Condo",
        "789 Hilltop Estate", "321 Riverside Loft",
        "654 Sunset Blvd Townhouse", "987 Park Avenue Penthouse",
    ],
    "Listing": [
        "MLS#2025-4821 Waterfront Home", "MLS#2025-7293 Downtown Studio",
        "MLS#2025-5618 Suburban Ranch", "MLS#2025-3047 Mountain Cabin",
        "MLS#2025-8156 Urban Duplex", "MLS#2025-2394 Farm Estate",
    ],
    "Agent": [
        "Jennifer Walsh, Realtor", "Marcus Thompson, Broker",
        "Sandra Liu, CCIM", "David Brennan, CRS",
        "Amy Richardson, ABR", "Kevin Ortiz, SRS",
    ],
    "Inspection": [
        "Pre-Purchase Home Inspection", "Termite and Pest Report",
        "Foundation Assessment", "Roof Condition Survey",
        "HVAC System Evaluation", "Plumbing Inspection",
    ],
    "Neighborhood": [
        "Willow Creek Estates", "Downtown Arts District",
        "Harbour Point", "Cedar Hills", "University Quarter",
        "Lakeside Commons",
    ],
    # Manufacturing
    "Machine": [
        "CNC Mill Station A3", "Hydraulic Press HP-200",
        "Laser Cutter LC-5000", "Assembly Robot AR-12",
        "Injection Molder IM-800", "Packaging Line PL-3",
    ],
    "Part": [
        "Titanium Gear Assembly TGA-401", "Steel Bearing Housing SBH-220",
        "Aluminum Heat Sink AHS-150", "Carbon Fiber Panel CFP-88",
        "Precision Valve PV-610", "Rubber Gasket Set RGS-44",
    ],
    "WorkOrder": [
        "WO-2025-0412 Batch Production", "WO-2025-0587 Custom Fabrication",
        "WO-2025-0721 Maintenance Overhaul", "WO-2025-0893 Quality Rework",
        "WO-2025-1045 Prototype Build", "WO-2025-1198 Emergency Repair",
    ],
    "Supplier": [
        "Pacific Steel Corp", "Rhine Valley Components",
        "Shanghai Precision Parts", "Great Lakes Polymers",
        "Nordic Metals AB", "Atlas Industrial Supply",
    ],
    "QualityReport": [
        "QR-2025-041 Dimensional Check", "QR-2025-078 Material Test",
        "QR-2025-112 Surface Finish Audit", "QR-2025-156 Stress Analysis",
    ],
    "ProductionLine": [
        "Line A - High Volume", "Line B - Custom Orders",
        "Line C - Precision Parts", "Line D - Assembly",
    ],
    # Conservation
    "Species": [
        "African Elephant (Loxodonta africana)", "Bengal Tiger (Panthera tigris tigris)",
        "Blue Whale (Balaenoptera musculus)", "Giant Panda (Ailuropoda melanoleuca)",
        "Monarch Butterfly (Danaus plexippus)", "Gray Wolf (Canis lupus)",
        "Green Sea Turtle (Chelonia mydas)", "Snow Leopard (Panthera uncia)",
    ],
    "Site": [
        "Yellowstone Corridor", "Amazon Basin Reserve",
        "Coral Triangle Marine Sanctuary", "Serengeti Conservation Area",
        "Borneo Rainforest Preserve", "Arctic Tundra Research Station",
    ],
    "Program": [
        "Wildlife Corridor Restoration", "Anti-Poaching Patrol Network",
        "Species Recovery Program", "Habitat Reforestation Initiative",
        "Marine Protected Area Management", "Community Conservation Partnership",
    ],
    "Funding": [
        "WWF Grant #G-2025-4821", "National Geographic Society Award",
        "EPA Conservation Fund", "Private Foundation Endowment",
        "Government Habitat Protection Grant", "Corporate Sustainability Pledge",
    ],
    "Monitoring": [
        "GPS Collar Tracking Study", "Camera Trap Survey",
        "Water Quality Assessment", "Population Census 2025",
        "Migration Pattern Analysis", "Vegetation Cover Mapping",
    ],
    # Data Journalism
    "Source": [
        "Federal Budget Database 2025", "Census Bureau ACS 5-Year",
        "SEC EDGAR Filings", "EPA Toxic Release Inventory",
        "FBI Uniform Crime Reports", "Medicare Provider Data",
    ],
    "Story": [
        "Investigation: Corporate Tax Havens", "Analysis: Housing Affordability Crisis",
        "Deep Dive: Police Use of Force Data", "Exposé: Water Contamination Risk",
        "Series: Healthcare Deserts in Rural America",
    ],
    "Dataset": [
        "Municipal Spending 2020-2025", "Campaign Finance Records",
        "Public School Performance Metrics", "Air Quality Index by County",
        "Hospital Readmission Rates", "Lobbying Disclosure Reports",
    ],
    "Claim": [
        "Claim: Unemployment Rate Trending Down", "Claim: Tax Reform Revenue Neutral",
        "Claim: Crime Rates at Historic Low", "Claim: Renewable Energy Cost Parity",
    ],
    "Investigation": [
        "INV-2025-01 Shell Company Network", "INV-2025-02 Procurement Fraud Pattern",
        "INV-2025-03 Environmental Violations", "INV-2025-04 Campaign Finance Links",
    ],
    # --- Agent Memory ---
    "Conversation": [
        "Customer Onboarding Chat", "Technical Support Session", "Product Discovery Thread",
        "Bug Report Discussion", "Weekly Standup Recap", "Architecture Design Review",
        "Sales Pipeline Review", "Security Incident Response",
    ],
    "Memory": [
        "User Preference: Dark Mode", "Context: Previous Order History",
        "Learned: Communication Style", "Fact: Team Size is 12",
        "User Goal: Reduce Response Time", "Insight: Peak Usage at 2PM",
        "Rule: Confirm Before Delete", "Pattern: Monday Morning Queries",
    ],
    "Session": [
        "Morning Briefing 2025-01-15", "API Debug Session", "Data Migration Planning",
        "Customer Demo Walkthrough", "Incident Triage #847", "Code Review Sprint-42",
        "Quarterly Planning Q1", "Integration Testing Run",
    ],
    "ToolCall": [
        "search_knowledge_base(auth)", "create_ticket(high priority)",
        "fetch_metrics(api service)", "run_query(MATCH nodes)",
        "send_notification(ops channel)", "analyze_logs(last hour)",
        "update_config(timeout)", "generate_report(weekly)",
    ],
    "Entity": [
        "Acme Corporation", "Project Phoenix", "Q1 Revenue Target",
        "Customer Segment Alpha", "Production Database", "Main API Gateway",
        "Marketing Campaign Q2", "Security Audit 2025",
    ],
    # --- Digital Twin ---
    "Alert": [
        "Temperature Threshold Exceeded", "Vibration Anomaly Detected",
        "Pressure Drop Warning", "Communication Timeout",
        "Calibration Drift Alert", "Power Fluctuation Warning",
        "Humidity Out of Range", "Flow Rate Deviation",
    ],
    "Asset": [
        "Industrial Compressor C-401", "Cooling Tower CT-3", "Boiler Unit B-102",
        "Generator Set GS-7", "HVAC System Zone 5", "Pump Station PS-12",
        "Conveyor Belt CB-8", "Transformer T-220", "Reactor Vessel RV-3",
    ],
    "MaintenanceRecord": [
        "Quarterly Calibration MR-101", "Bearing Replacement MR-102",
        "Firmware Update v2.4 MR-103", "Emergency Valve Repair MR-104",
        "Scheduled Lubrication MR-105", "Sensor Swap-Out MR-106",
        "Filter Replacement MR-107", "Wiring Inspection MR-108",
    ],
    "Reading": [
        "Temp 72.4F Boiler #3", "Pressure 14.7 PSI Valve 12",
        "Vibration 0.05mm/s Motor A", "Flow 120 GPM Pipeline North",
        "Humidity 65% Warehouse B", "Voltage 480V Panel C",
        "RPM 1750 Pump Station", "pH 7.2 Treatment Plant",
    ],
    "Sensor": [
        "Thermocouple TC-201", "Pressure Transducer PT-105",
        "Accelerometer ACC-308", "Flow Meter FM-042",
        "Humidity Probe HP-156", "Voltage Monitor VM-089",
        "Tachometer TAC-220", "pH Sensor PH-015",
    ],
    "System": [
        "Building Management System", "Process Control Network",
        "Energy Management Platform", "Predictive Maintenance Hub",
        "Environmental Monitoring Array", "Safety Interlock System",
        "Quality Assurance Network", "Asset Tracking Platform",
    ],
    # --- Golf Sports ---
    "Round": [
        "Championship Final Round", "Saturday Morning 18",
        "Pro-Am Charity Round", "Qualifying Round 1",
        "Club Championship Semifinal", "Twilight 9-Hole",
        "Winter League Round 8", "Member-Guest Best Ball",
    ],
    "Handicap": [
        "Active HCP 12.4", "Active HCP 5.8", "Active HCP 18.2",
        "Active HCP 24.1", "Active HCP 8.6", "Active HCP 15.3",
        "Active HCP 2.1", "Active HCP 30.5",
    ],
    "Hole": [
        "The Island Green (Par 3)", "Amen Corner (Par 4)",
        "Devil's Elbow (Par 5)", "Lighthouse View (Par 3)",
        "The Narrows (Par 4)", "Eagle's Nest (Par 5)",
        "Bunker Hill (Par 4)", "The Pond Hole (Par 3)",
    ],
    "Course": [
        "Augusta National Golf Club", "Pebble Beach Golf Links",
        "St Andrews Old Course", "Pine Valley Golf Club",
        "Cypress Point Club", "Royal Melbourne Golf Club",
        "Shinnecock Hills Golf Club", "Muirfield Golf Links",
    ],
    "Tournament": [
        "The Masters 2025", "US Open Championship",
        "The Open Championship", "PGA Championship",
        "Ryder Cup 2025", "Presidents Cup",
        "Players Championship", "FedEx Cup Playoffs",
    ],
    # --- Hospitality ---
    "Room": [
        "Oceanview Suite 801", "Standard King 412", "Deluxe Double 305",
        "Presidential Suite 1201", "Garden View Twin 218",
        "Executive Corner 610", "Accessible King 102",
        "Penthouse Suite 1501", "Economy Single 203", "Family Room 507",
    ],
    "Reservation": [
        "RES-4821 Johnson 3 nights", "RES-7293 Park Weekend",
        "RES-5618 Garcia Corporate", "RES-3047 Smith Anniversary",
        "RES-8156 Lee Group Block", "RES-2394 Brown Extended Stay",
        "RES-1756 Wilson Last-Minute", "RES-9203 Chen Holiday",
    ],
    "Guest": [
        "Margaret Chen", "David Okonkwo", "Sofia Petrov", "James Nakamura",
        "Amira Hassan", "Robert Lindqvist", "Isabella Rossi", "Thomas Adebayo",
        "Yuki Tanaka", "Priya Kapoor",
    ],
    "Staff": [
        "Concierge Maria Santos", "Manager Robert Kim", "Chef Antoine Blanc",
        "Housekeeping Lead Aisha Patel", "Front Desk Agent Tom Walsh",
        "Spa Director Lucia Fernandez", "Valet Captain James Osei",
        "Events Coordinator Sarah Blake",
    ],
    # --- Oil & Gas ---
    "Permit": [
        "DRL-0142 Drilling Permit", "ENV-0287 Environmental Clearance",
        "FLR-0351 Flaring Permit", "WDL-0419 Water Disposal License",
        "PLN-0508 Pipeline Right-of-Way", "OPS-0623 Operations Permit",
        "SEI-0912 Seismic Survey Permit", "PRD-1003 Production License",
    ],
    "Well": [
        "Permian Basin Well #47", "Eagle Ford Shale W-12",
        "Bakken Formation Well #103", "Marcellus Shale W-28",
        "Gulf Deepwater Well DW-6", "Prudhoe Bay Well PB-19",
        "Delaware Basin Well #82", "Haynesville Shale W-55",
    ],
    "Equipment": [
        "Drilling Rig DR-15", "Mud Pump MP-7", "BOP Stack BOP-42",
        "Christmas Tree CT-18", "Separator Unit SEP-9", "Compressor CS-23",
        "Pipeline Pig Launcher PL-3", "Flare Stack FS-11",
    ],
    "Reservoir": [
        "Ghawar Field Reservoir", "Permian Basin Formation A",
        "North Sea Brent Reservoir", "Kashagan Field Layer 3",
        "Marcellus Shale Zone B", "Eagle Ford Sweet Spot",
        "Bakken Middle Formation", "Wolfcamp A Bench",
    ],
    "Formation": [
        "Wolfcamp Shale", "Spraberry Formation", "Bone Spring Limestone",
        "Delaware Mountain Group", "Austin Chalk", "Niobrara Formation",
        "Woodford Shale", "Tuscaloosa Marine Shale",
    ],
    # --- Personal Knowledge ---
    "JournalEntry": [
        "Reflections on Q1 Goals", "Book Notes: Thinking Fast and Slow",
        "Meeting Takeaways Board Review", "Travel Journal Kyoto Day 3",
        "Weekly Review: Productivity Wins", "Ideas for Side Project",
        "Gratitude Log March 2025", "Learning Notes: Rust Ownership",
    ],
    "Note": [
        "API Design Best Practices", "Conference Talk Ideas",
        "Recipe: Homemade Ramen", "Workout Routine Week 12",
        "Investment Research Notes", "Reading List Q2 2025",
        "Home Renovation Plans", "Garden Planting Schedule",
    ],
    "Bookmark": [
        "Hacker News: Distributed Systems", "ArXiv: Attention Is All You Need",
        "MDN Web Docs: Fetch API", "Neo4j Graph Academy",
        "Rust Book Chapter 10", "AWS Well-Architected Guide",
        "Martin Fowler: Refactoring Catalog", "OWASP Top 10",
    ],
    "Contact": [
        "Dr. Sarah Mitchell (Mentor)", "Alex Rivera (Collaborator)",
        "Prof. James Wu (Advisor)", "Lisa Park (Editor)",
        "David Okafor (CTO)", "Maria Santos (Designer)",
        "Tom Chen (Investor)", "Aisha Patel (Legal Counsel)",
    ],
    "Topic": [
        "Machine Learning Fundamentals", "Graph Database Design",
        "Personal Finance Strategy", "Creative Writing Techniques",
        "Home Automation Setup", "Fitness and Nutrition",
        "Travel Photography Tips", "Sustainable Living",
    ],
    "Project": [
        "Personal Knowledge Graph", "Open Source CLI Tool",
        "Home Automation Dashboard", "Photography Portfolio",
        "Language Learning App", "Community Garden Website",
        "Podcast Production Setup", "Family Recipe Archive",
    ],
    # --- Retail E-commerce ---
    "Order": [
        "ORD-4821 Electronics Bundle", "ORD-7293 Seasonal Sale",
        "ORD-5618 Subscription Renewal", "ORD-3047 Gift Registry",
        "ORD-8156 Bulk Office Supplies", "ORD-2394 Returns Exchange",
        "ORD-1756 Express Delivery", "ORD-9203 Wholesale Order",
    ],
    "Product": [
        "Wireless Noise-Cancelling Headphones", "Organic Cotton T-Shirt",
        "Smart Home Hub Pro", "Stainless Steel Water Bottle",
        "Ergonomic Office Chair", "Portable Bluetooth Speaker",
        "Premium Running Shoes", "Bamboo Cutting Board Set",
    ],
    "Customer": [
        "Sarah Chen (Premium)", "Marcus Johnson (Standard)",
        "Elena Volkov (VIP)", "James Obi (New Customer)",
        "Priya Sharma (Loyalty Gold)", "Robert Kim (Business)",
        "Isabella Rossi (Returning)", "David Tanaka (Wholesale)",
    ],
    "Campaign": [
        "Summer Sale 2025", "Black Friday Deals", "New Customer Welcome",
        "Loyalty Program Launch", "Flash Sale: Electronics",
        "Holiday Gift Guide", "Back to School", "Spring Clearance",
    ],
    "Category": [
        "Electronics & Gadgets", "Clothing & Apparel", "Home & Garden",
        "Sports & Outdoors", "Books & Media", "Health & Beauty",
        "Toys & Games", "Food & Beverages",
    ],
    # --- Vacation Industry ---
    "Booking": [
        "Caribbean Cruise BK-4821", "Ski Resort Package BK-7293",
        "Safari Adventure BK-5618", "Island Getaway BK-3047",
        "European Tour BK-8156", "Honeymoon Suite BK-2394",
        "Family Beach Vacation BK-1756", "Wellness Retreat BK-9203",
    ],
    "Package": [
        "All-Inclusive Paradise", "Adventure Explorer",
        "Luxury Spa Retreat", "Family Fun Bundle",
        "Romantic Getaway", "Backpacker Special",
        "Cultural Immersion Tour", "Eco-Lodge Experience",
    ],
    "Resort": [
        "Four Seasons Bora Bora", "Sandals Royal Barbados",
        "Aman Tokyo", "Six Senses Zighy Bay",
        "One&Only Reethi Rah", "Banyan Tree Phuket",
        "Rosewood Mayakoba", "Belmond Cap Juluca",
    ],
    "Season": [
        "Peak Summer 2025", "Holiday Season 2025",
        "Spring Break 2025", "Shoulder Season Fall",
        "Winter Ski Season", "Monsoon Off-Peak",
        "Cherry Blossom Season", "Whale Watching Season",
    ],
    # --- Wildlife Management ---
    "Sighting": [
        "Bengal Tiger at Watering Hole", "Elephant Herd Migration Path",
        "Snow Leopard Ridge Camera #7", "Wolf Pack at Elk Crossing",
        "Rhino Mother-Calf Pair Zone B", "Gorilla Troop Bamboo Forest",
        "Sea Turtle Nesting Event", "Condor Thermal Soaring Peak 4",
    ],
    "Camera": [
        "Trail Cam TC-201 North Ridge", "Waterhole Station WH-105",
        "Canopy Cam CC-308 Sector 7", "Road Crossing Monitor RC-042",
        "Nest Box Cam NB-156", "Underwater Sensor UW-089",
        "Thermal Imaging Unit TI-220", "Night Vision Station NV-312",
    ],
    "Habitat": [
        "Tropical Rainforest Canopy", "African Savanna Grassland",
        "Arctic Tundra Zone", "Coral Reef Shelf",
        "Mangrove Estuary Delta", "Temperate Deciduous Forest",
        "Alpine Meadow Corridor", "Deep Ocean Vent Community",
    ],
    "Individual": [
        "Bengal Tiger Raja (#BT-047)", "African Elephant Tembo (#AE-112)",
        "Snow Leopard Ghost (#SL-008)", "Gray Wolf Alpha (#GW-031)",
        "Mountain Gorilla Bwindi (#MG-019)", "Sea Turtle Kai (#ST-203)",
        "Giant Panda Ming (#GP-055)", "Polar Bear Nanuk (#PB-014)",
    ],
    "Threat": [
        "Poaching Ring Eastern Sector", "Habitat Fragmentation Highway Expansion",
        "Climate Change: Glacial Retreat", "Invasive Species: Water Hyacinth",
        "Pollution: River Mercury Contamination", "Human-Wildlife Conflict Zone C",
        "Disease: Avian Influenza Outbreak", "Illegal Logging Western Reserve",
    ],
    # --- Data Journalism ---
    "Correction": [
        "Revenue Figure Correction Q3", "Date Error in Timeline",
        "Misattributed Quote Fix", "Statistical Methodology Update",
        "Source Name Correction", "Geographic Data Fix",
        "Inflation-Adjusted Figures", "Updated Election Results",
    ],
    # --- Conservation (additional) ---
    "Stakeholder": [
        "World Wildlife Fund", "Ministry of Environment",
        "Local Indigenous Council", "International Conservation Alliance",
        "Regional Wildlife Authority", "Eco-Tourism Cooperative",
        "University Research Partnership", "Corporate Sustainability Sponsor",
    ],
    # --- GIS Cartography ---
    "Boundary": [
        "National Park Perimeter", "Municipal District Line",
        "Protected Wetland Zone", "Agricultural Land Boundary",
        "Coastal Erosion Zone", "Forest Reserve Boundary",
        "Indigenous Territory Limit", "Flood Plain Demarcation",
    ],
    "Coordinate": [
        "Summit Peak A (47.3N, 11.1E)", "River Confluence Point",
        "Survey Marker SM-442", "GPS Station CORS-017",
        "Tidal Gauge Station TG-5", "Weather Station WX-28",
        "Seismic Monitor SM-103", "Benchmark BM-7721",
    ],
    "Feature": [
        "Mountain Ridge Alpine A", "Lake Victoria Shoreline",
        "Highway I-95 Corridor", "River Delta Formation",
        "Volcanic Crater Zone", "Karst Cave System",
        "Barrier Island Chain", "Glacial Moraine Field",
    ],
    "Layer": [
        "Topographic Contours 10m", "Land Use Classification",
        "Hydrological Network", "Soil Type Distribution",
        "Vegetation Cover Index", "Transportation Network",
        "Population Density Heat Map", "Geological Formation Map",
    ],
    "MapProject": [
        "City Master Plan 2030", "Flood Risk Assessment",
        "Conservation Corridor Map", "Urban Heat Island Study",
        "Archaeological Survey Grid", "Wildfire Risk Zones",
        "Transit Network Expansion", "Coastal Resilience Atlas",
    ],
    "Survey": [
        "Cadastral Survey District 7", "Topographic Survey Block A",
        "Environmental Impact Survey", "Archaeological Field Survey",
        "Geodetic Control Survey", "Bathymetric Survey Sector 3",
        "LiDAR Aerial Survey Run 12", "Ground-Penetrating Radar Survey",
    ],
    # --- GenAI LLM Ops ---
    "Model": [
        "GPT-4o Production", "Claude Sonnet Fine-tuned",
        "Llama 3 70B Local", "Mistral 7B Instruct",
        "Gemini Pro 1.5", "DBRX Base",
        "Phi-3 Mini Quantized", "Command R+ RAG",
    ],
    "Prompt": [
        "System Prompt: Customer Support Agent", "Few-Shot: Code Review",
        "Chain-of-Thought: Math Reasoning", "RAG: Document QA",
        "Tool Use: API Integration", "Structured Output: JSON Schema",
        "Multi-turn: Dialogue Management", "Safety: Content Filter",
    ],
    "Evaluation": [
        "MMLU Benchmark Run", "HumanEval Code Gen",
        "TruthfulQA Assessment", "GSM8K Math Eval",
        "MT-Bench Conversation", "Safety Red Team Eval",
        "Latency Benchmark P99", "Cost Efficiency Analysis",
    ],
    "Experiment": [
        "Fine-tuning Run FT-042", "RAG Pipeline Comparison",
        "Prompt Engineering A/B Test", "Temperature Sweep Study",
        "Context Window Scaling", "Few-Shot vs Zero-Shot",
        "Model Distillation Trial", "Embedding Model Benchmark",
    ],
    # --- Product Management ---
    "Epic": [
        "User Onboarding Redesign", "Payment System Migration",
        "Mobile App v3.0", "API Platform Launch",
        "Analytics Dashboard Overhaul", "Accessibility Compliance",
        "Performance Optimization Sprint", "Multi-Language Support",
    ],
    "Metric": [
        "Monthly Active Users (MAU)", "Net Promoter Score (NPS)",
        "Customer Acquisition Cost (CAC)", "Monthly Recurring Revenue (MRR)",
        "Churn Rate", "Time to First Value (TTFV)",
        "Feature Adoption Rate", "Customer Lifetime Value (CLV)",
    ],
    "Objective": [
        "Increase user retention by 15%", "Reduce onboarding time to 3 min",
        "Launch enterprise tier Q2", "Achieve SOC 2 compliance",
        "Scale to 100K concurrent users", "Reduce support tickets by 30%",
        "Improve NPS to 60+", "Zero-downtime deployments",
    ],
    "Release": [
        "v2.5.0 Performance Release", "v3.0.0 Major Redesign",
        "v2.6.1 Hotfix: Auth Bug", "v2.7.0 API v2 Launch",
        "v3.1.0 Mobile Parity", "v2.8.0 Analytics Suite",
        "v3.0.1 Security Patch", "v2.9.0 Internationalization",
    ],
    "Feedback": [
        "User Interview: Enterprise Buyer", "NPS Survey Response Batch 47",
        "Beta Tester: Performance Issues", "Support Ticket Trend Analysis",
        "Usability Test: Checkout Flow", "App Store Review Summary",
        "Customer Advisory Board Q1", "Churn Exit Interview Insights",
    ],
    "UserPersona": [
        "Sarah the Startup Founder", "David the Enterprise Admin",
        "Priya the Power User", "James the Casual Browser",
        "Elena the Technical Lead", "Marcus the New Employee",
        "Yuki the Small Business Owner", "Robert the Compliance Officer",
    ],
    # --- Scientific Research ---
    "Paper": [
        "Graph Neural Networks for Drug Discovery", "Quantum Error Correction at Scale",
        "mRNA Vaccine Stability Optimization", "Dark Matter Detection via Gravitational Lensing",
        "CRISPR Off-Target Effects Meta-Analysis", "Exoplanet Atmospheric Spectroscopy",
        "Neuroplasticity in Adult Learning", "Carbon Capture Efficiency Benchmarks",
    ],
    "Researcher": [
        "Dr. Sarah Chen (Genomics)", "Prof. James Okafor (Physics)",
        "Dr. Elena Volkov (Neuroscience)", "Prof. Raj Patel (Materials Science)",
        "Dr. Maria Santos (Epidemiology)", "Prof. David Kim (Computer Science)",
        "Dr. Aisha Hassan (Climate)", "Prof. Thomas Mueller (Chemistry)",
    ],
    "Grant": [
        "NIH R01 Grant #GM-123456", "NSF CAREER Award #2025-789",
        "ERC Starting Grant #101034", "DARPA Contract #HR0011-25",
        "DOE ARPA-E Award #DE-0042", "Wellcome Trust Grant #225801",
        "Gates Foundation Grant #INV-047", "HHMI Investigator Award",
    ],
    "Institution": [
        "MIT Lincoln Laboratory", "Stanford Bio-X Institute",
        "CERN European Particle Physics", "Max Planck Institute",
        "Oxford Nanopore Research", "Broad Institute of MIT and Harvard",
        "Caltech Jet Propulsion Lab", "Salk Institute for Biological Studies",
    ],
    # Options Intelligence
    "Underlying": [
        "S&P 500 Index", "SPDR S&P 500 ETF", "Invesco QQQ Trust",
        "iShares Russell 2000", "Apple Inc", "NVIDIA Corporation",
        "Tesla Inc", "Amazon.com Inc", "Meta Platforms",
        "Microsoft Corporation", "Alphabet Inc", "AMD",
    ],
    "OptionsContract": [
        "SPX 5800C 0DTE", "SPX 5750P 0DTE", "SPY 580C Weekly",
        "SPY 575P Weekly", "QQQ 500C 0DTE", "QQQ 495P 0DTE",
        "TSLA 250C Weekly", "NVDA 140C 0DTE", "AAPL 230P Weekly",
        "SPX 5700P 0DTE", "SPX 5850C 0DTE", "SPY 585C 0DTE",
    ],
    "ExposureLevel": [
        "GEX @ 5800", "GEX @ 5750", "GEX @ 5850", "GEX @ 5700",
        "DEX @ 5800", "DEX @ 5750", "VEX @ 5800", "CHEX @ 5750",
        "GEX @ 580 SPY", "GEX @ 575 SPY", "GEX @ 500 QQQ",
        "GEX @ 495 QQQ",
    ],
    "Regime": [
        "Positive Gamma Regime", "Negative Gamma Regime",
        "Transition Regime", "Neutral Regime",
        "Post-FOMC Positive Gamma", "Pre-CPI Negative Gamma",
        "Expiration Pin Regime", "VIX Spike Transition",
    ],
    "KeyLevel": [
        "SPX Put Wall 5700", "SPX Call Wall 5850", "SPX Gamma Flip 5780",
        "SPX Magnet 5800", "SPY Put Wall 575", "SPY Call Wall 585",
        "QQQ Support 495", "QQQ Resistance 505",
        "SPX Vol Trigger 5750", "SPX HVL 5810",
    ],
    "Trade": [
        "SPX 5800C Scalp Long", "SPX 5750P Directional Short",
        "SPY Iron Condor 575-585", "QQQ Straddle 500",
        "SPX Butterfly 5780-5800-5820", "TSLA 250C Momentum Long",
        "SPX 5700P Hedge Buy", "SPY 580-585 Call Spread",
    ],
    "MarketEvent": [
        "FOMC Rate Decision Jan 2026", "CPI Release Feb 2026",
        "NFP Report Jan 2026", "NVIDIA Earnings Q4 2025",
        "Monthly OpEx Jan 2026", "VIX Spike 28 Jan 15",
        "SPX Regime Flip Jan 16", "PPI Release Jan 2026",
    ],
    "Strategy": [
        "0DTE Gamma Scalp", "Negative Gamma Mean Reversion",
        "Put Wall Bounce", "Call Wall Fade", "FOMC Straddle",
        "Pin Risk Butterfly", "Momentum Breakout", "VIX Spike Fade",
    ],
}

# Mapping of entity labels to preferred ID prefixes
LABEL_ID_PREFIXES: dict[str, str] = {
    "Patient": "PAT", "Provider": "PRV", "Diagnosis": "DX",
    "Medication": "MED", "Treatment": "TRT", "Encounter": "ENC",
    "Account": "ACT", "Transaction": "TXN", "Security": "SEC",
    "Repository": "REPO", "Issue": "ISS", "PullRequest": "PR",
    "Deployment": "DEP", "Incident": "INC", "Service": "SVC",
    "Player": "PLY", "Character": "CHR", "Item": "ITM",
    "Quest": "QST", "Guild": "GLD", "Achievement": "ACH",
    "Property": "PRP", "Listing": "LST", "Machine": "MCH",
    "Part": "PRT", "WorkOrder": "WO", "Supplier": "SUP",
    "Species": "SPE", "Site": "SIT", "Program": "PRG",
    "Source": "SRC", "Story": "STR", "Dataset": "DS",
    "Destination": "DST", "Hotel": "HTL", "Activity": "ACT",
    "Underlying": "UND", "OptionsContract": "OPT", "ExposureLevel": "EXP",
    "Regime": "REG", "KeyLevel": "KLV", "Trade": "TRD",
    "MarketEvent": "MEV", "Strategy": "STG",
}

# ---------------------------------------------------------------------------
# Property name patterns for contextual value generation
# ---------------------------------------------------------------------------

_EMAIL_PROPERTIES = {"email", "email_address", "contact_email"}
_PHONE_PROPERTIES = {"phone", "phone_number", "contact_phone", "telephone"}
_URL_PROPERTIES = {"url", "website", "homepage", "link"}
_ADDRESS_PROPERTIES = {"address", "street_address", "location_address"}
_DESCRIPTION_PROPERTIES = {"description", "summary", "notes", "details", "bio"}
_ID_PROPERTIES = {"id", "code", "number", "identifier"}

_STREETS = [
    "123 Main Street", "456 Oak Avenue", "789 Pine Boulevard",
    "321 Maple Drive", "654 Cedar Lane", "987 Elm Court",
    "147 Birch Road", "258 Willow Way", "369 Spruce Circle",
    "741 Chestnut Terrace",
]

_CITIES = [
    "San Francisco, CA 94105", "New York, NY 10001", "Chicago, IL 60601",
    "Austin, TX 78701", "Seattle, WA 98101", "Boston, MA 02101",
    "Denver, CO 80202", "Portland, OR 97201", "Miami, FL 33101",
    "Atlanta, GA 30301",
]

_ROLE_POOL = [
    "Senior Analyst", "Project Manager", "Technical Lead",
    "Research Director", "Operations Manager", "Chief Strategist",
    "Field Coordinator", "Quality Assurance Lead", "Data Scientist",
    "Solutions Architect", "Program Director", "Compliance Officer",
]

_INDUSTRY_POOL = [
    "Technology", "Healthcare", "Financial Services", "Manufacturing",
    "Energy", "Consulting", "Real Estate", "Education",
    "Environmental Services", "Logistics",
]

DOMAIN_INDUSTRY_POOL: dict[str, list[str]] = {
    "healthcare": [
        "Hospital Systems", "Medical Devices", "Pharmaceuticals",
        "Health Insurance", "Clinical Research", "Telemedicine",
    ],
    "financial-services": [
        "Banking", "Insurance", "Asset Management", "Fintech",
        "Investment Banking", "Private Equity",
    ],
    "gaming": [
        "Game Development", "Esports", "Game Publishing",
        "Interactive Entertainment", "Game Streaming", "Game Analytics",
    ],
    "software-engineering": [
        "Software Development", "Cloud Computing", "Cybersecurity",
        "DevOps", "SaaS", "Open Source",
    ],
    "conservation": [
        "Conservation", "Wildlife Services", "Environmental Research",
        "Park Management", "Ecological Consulting", "Marine Biology",
    ],
    "data-journalism": [
        "Investigative Journalism", "Data Analytics", "News Media",
        "Publishing", "Digital Media", "Public Interest Research",
    ],
    "manufacturing": [
        "Industrial Manufacturing", "Automotive", "Aerospace",
        "Process Engineering", "Supply Chain", "Quality Assurance",
    ],
    "real-estate": [
        "Residential Real Estate", "Commercial Real Estate", "Property Management",
        "Real Estate Investment", "Urban Development", "Construction",
    ],
    "trip-planning": [
        "Travel & Tourism", "Hospitality", "Tour Operations",
        "Travel Technology", "Destination Marketing", "Adventure Travel",
    ],
    "wildlife-management": [
        "Wildlife Conservation", "Habitat Management", "Animal Welfare",
        "Ecological Services", "Biodiversity Research", "Forest Management",
    ],
    "scientific-research": [
        "Biotechnology", "Pharmaceutical Research", "Academic Research",
        "Laboratory Services", "Scientific Publishing", "R&D",
    ],
    "oil-gas": [
        "Oil & Gas Exploration", "Petroleum Engineering", "Energy Services",
        "Pipeline Operations", "Refining", "Upstream Operations",
    ],
    "retail-ecommerce": [
        "E-Commerce", "Retail Technology", "Consumer Goods",
        "Marketplace Operations", "Logistics & Fulfillment", "Digital Retail",
    ],
    "hospitality": [
        "Hospitality Management", "Hotel Operations", "Restaurant Services",
        "Event Management", "Resort Operations", "Food & Beverage",
    ],
    "digital-twin": [
        "Digital Twin Technology", "IoT", "Simulation Engineering",
        "Smart Manufacturing", "Predictive Analytics", "Industrial IoT",
    ],
    "genai-llm-ops": [
        "AI/ML Operations", "LLM Infrastructure", "AI Research",
        "Machine Learning", "NLP Services", "AI Platform",
    ],
    "gis-cartography": [
        "Geospatial Services", "Cartography", "GIS Technology",
        "Remote Sensing", "Surveying", "Spatial Analytics",
    ],
    "golf-sports": [
        "Sports Management", "Golf Club Operations", "Sports Technology",
        "Athletic Training", "Sports Analytics", "Event Management",
    ],
    "personal-knowledge": [
        "Knowledge Management", "Personal Productivity", "EdTech",
        "Information Services", "Content Organization", "Learning Platforms",
    ],
    "product-management": [
        "Product Development", "Software Products", "Product Analytics",
        "UX Research", "Product Strategy", "Growth Engineering",
    ],
    "vacation-industry": [
        "Vacation Rentals", "Tourism", "Travel Services",
        "Resort Management", "Leisure & Recreation", "Destination Services",
    ],
    "agent-memory": [
        "AI Systems", "Memory Architecture", "Agent Infrastructure",
        "Cognitive Computing", "AI Research", "Knowledge Systems",
    ],
    "options-intelligence": [
        "Options Trading", "Derivatives Analysis", "Market Microstructure",
        "Volatility Research", "Dealer Positioning", "Gamma Exposure Analytics",
    ],
}

_CURRENCY_POOL = ["USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR", "BRL"]

_TICKER_POOL = [
    "SPX", "SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "JPM", "BAC", "WMT", "JNJ", "PG", "UNH", "V", "HD", "MA", "DIS",
    "NVDA", "PFE", "KO",
]

_DRUG_CLASS_POOL = [
    "Biguanide", "ACE Inhibitor", "Statin", "Beta-Blocker", "SSRI",
    "Anticoagulant", "Proton Pump Inhibitor", "Calcium Channel Blocker",
    "Opioid Analgesic", "Benzodiazepine", "Diuretic", "Corticosteroid",
]

_STATUS_POOL = ["active", "inactive", "pending", "completed", "in_progress", "under_review"]

_SEVERITY_POOL = ["low", "medium", "high", "critical"]

_LANGUAGE_POOL = [
    "English", "Spanish", "French", "Mandarin", "German",
    "Japanese", "Portuguese", "Arabic", "Hindi", "Korean",
]

_COUNTRY_POOL = [
    "United States", "United Kingdom", "Canada", "Germany", "France",
    "Japan", "Australia", "Brazil", "India", "South Korea",
    "Mexico", "Italy", "Spain", "Netherlands", "Sweden",
]

_COMPLAINT_POOL = [
    "Chest pain", "Shortness of breath", "Headache", "Abdominal pain",
    "Back pain", "Fever", "Cough", "Dizziness", "Fatigue",
    "Joint pain", "Nausea", "Skin rash",
]

_DISPOSITION_POOL = [
    "Discharged", "Admitted", "Transferred", "Observation",
    "Against Medical Advice", "Follow-up scheduled",
]

_SPECIALTY_POOL = [
    "Cardiology", "Oncology", "Neurology", "Orthopedics",
    "Pediatrics", "Internal Medicine", "Emergency Medicine",
    "Radiology", "Dermatology", "Psychiatry",
]

# ---------------------------------------------------------------------------
# Additional property value pools to replace templated "{name} - {prop}" pattern
# ---------------------------------------------------------------------------

_CONTRAINDICATION_POOL = [
    "Renal impairment (GFR < 30 mL/min)", "Hepatic dysfunction",
    "Pregnancy Category D", "Known hypersensitivity", "Active GI bleeding",
    "Severe bradycardia", "Concurrent MAO inhibitor use",
    "Uncontrolled diabetes", "History of angioedema", "Acute heart failure",
]

_DOSAGE_FORM_POOL = [
    "Tablet", "Capsule", "Injectable", "Oral Solution", "Topical Cream",
    "Inhaler", "Transdermal Patch", "Suppository", "Sublingual Tablet",
    "Extended-Release Tablet", "Chewable Tablet", "Nasal Spray",
]

_ALLERGY_POOL = [
    "Penicillin", "Sulfa drugs", "Latex", "Shellfish", "Aspirin",
    "Iodine contrast dye", "Codeine", "Tetracycline", "Egg proteins",
    "No known allergies", "NSAID sensitivity", "Peanuts",
]

_SECTOR_POOL = [
    "Technology", "Healthcare", "Financial Services", "Energy",
    "Consumer Discretionary", "Industrials", "Real Estate",
    "Utilities", "Materials", "Communications", "Consumer Staples",
]

_REPORTER_POOL = [
    "Alex Rivera", "Jordan Lee", "Casey Morgan", "Sam Patterson",
    "Taylor Singh", "Morgan Chen", "Dakota Williams", "Avery Johnson",
    "Quinn Martinez", "Riley Thompson", "Cameron Davis", "Drew Wilson",
]

# Domain-aware base entity pools — override generic POLE+O names when domain is known
DOMAIN_PERSON_NAMES: dict[str, list[str]] = {
    "healthcare": [
        "Dr. Sarah Chen", "Nurse James Morrison", "Dr. Maria Rodriguez",
        "Dr. David Park", "Nurse Elena Volkov", "Dr. Michael O'Brien",
        "Pharmacist Aisha Patel", "Dr. Robert Kim", "Nurse Lisa Nakamura",
        "Dr. Carlos Gutierrez", "Nurse Fatima Al-Hassan", "Dr. Thomas Weber",
    ],
    "financial-services": [
        "Portfolio Manager Sarah Chen", "Risk Analyst James Morrison",
        "Wealth Advisor Maria Rodriguez", "Compliance Officer David Park",
        "Trading Desk Lead Elena Volkov", "Senior Banker Michael O'Brien",
        "Financial Planner Aisha Patel", "Credit Analyst Robert Kim",
    ],
    "gaming": [
        "Game Designer Sarah C.", "Community Manager James M.",
        "QA Lead Maria R.", "Server Admin David P.",
        "Esports Coordinator Elena V.", "LiveOps Manager Michael O.",
    ],
    "software-engineering": [
        "Staff Engineer Sarah Chen", "SRE Lead James Morrison",
        "Principal Engineer Maria Rodriguez", "DevOps Manager David Park",
        "Security Engineer Elena Volkov", "Platform Lead Michael O'Brien",
    ],
    "conservation": [
        "Field Researcher Sarah Chen", "Park Ranger James Morrison",
        "Conservation Biologist Maria Rodriguez", "Wildlife Vet David Park",
        "GIS Analyst Elena Volkov", "Ecologist Michael O'Brien",
    ],
    "data-journalism": [
        "Senior Reporter Sarah Chen", "Investigative Journalist James Morrison",
        "Data Editor Maria Rodriguez", "FOIA Specialist David Park",
        "Graphics Editor Elena Volkov", "Fact-Checker Michael O'Brien",
    ],
}

DOMAIN_ORGANIZATION_NAMES: dict[str, list[str]] = {
    "healthcare": [
        "Metropolitan General Hospital", "Sunrise Medical Center",
        "Valley Health Network", "Pacific Medical Group",
        "Community Care Alliance", "University Hospital System",
    ],
    "financial-services": [
        "Global Capital Partners", "Pacific Ridge Investments",
        "Sterling Wealth Management", "Apex Securities Group",
        "First National Trust", "Harbor Point Capital",
    ],
    "gaming": [
        "Nexus Games Studio", "Titan Interactive",
        "Pixel Forge Entertainment", "Storm Cloud Games",
        "Digital Horizons Ltd", "Obsidian Play",
    ],
    "software-engineering": [
        "TechStream Inc", "CloudScale Systems",
        "DataPipe Solutions", "Nexus Platform Corp",
        "OpenGrid Technologies", "Quantum Cloud Inc",
    ],
}

DOMAIN_LOCATION_NAMES: dict[str, list[str]] = {
    "healthcare": [
        "Main Hospital Campus", "East Wing ICU", "Outpatient Clinic B",
        "Emergency Department", "Radiology Suite", "Pharmacy Building",
    ],
    "financial-services": [
        "Wall Street Trading Floor", "Midtown Advisory Office",
        "Downtown Branch", "Corporate Headquarters", "Data Center East",
    ],
    "gaming": [
        "NA-East Server Cluster", "EU-West Game Farm",
        "Asia-Pacific Data Center", "QA Testing Lab",
    ],
    "software-engineering": [
        "Production Datacenter", "Staging Environment",
        "CI/CD Build Farm", "Disaster Recovery Site",
    ],
}

DOMAIN_EVENT_NAMES: dict[str, list[str]] = {
    "healthcare": [
        "Grand Rounds Lecture", "Emergency Code Blue Drill",
        "Pharmacy & Therapeutics Committee", "Infection Control Audit",
        "Morbidity & Mortality Conference", "Nursing Education Seminar",
    ],
    "financial-services": [
        "Quarterly Earnings Call", "Fed Rate Decision Brief",
        "Risk Committee Meeting", "Portfolio Rebalancing Review",
        "Compliance Training Session", "Investor Conference",
    ],
    "gaming": [
        "Season 5 Launch Event", "Server Maintenance Window",
        "Community Tournament", "Patch Notes Livestream",
        "Beta Testing Phase", "Holiday In-Game Event",
    ],
    "software-engineering": [
        "Sprint Retrospective", "Incident Post-Mortem",
        "Architecture Review Board", "On-Call Handoff",
        "Production Deploy Window", "Chaos Engineering Day",
    ],
}

DOMAIN_OBJECT_NAMES: dict[str, list[str]] = {
    "healthcare": [
        "Patient Care Protocol", "Clinical Trial Report",
        "Medication Reconciliation Form", "Discharge Planning Checklist",
        "Lab Results Summary", "Radiology Findings Report",
    ],
    "financial-services": [
        "Risk Assessment Report", "Portfolio Performance Summary",
        "Compliance Filing", "Due Diligence Memo",
        "Quarterly Market Analysis", "Client Onboarding Package",
    ],
    "gaming": [
        "Game Design Document", "Balance Patch Notes",
        "Player Behavior Report", "Economy Audit Spreadsheet",
        "Server Performance Log", "Community Feedback Summary",
    ],
    "software-engineering": [
        "Architecture Decision Record", "Incident Report",
        "Runbook for Database Failover", "API Specification",
        "Load Test Results", "Security Audit Findings",
    ],
}

DOMAIN_ROLE_POOL: dict[str, list[str]] = {
    "healthcare": [
        "Attending Physician", "Charge Nurse", "Resident", "Pharmacist",
        "Lab Technician", "Radiologist", "Physical Therapist", "Surgeon",
    ],
    "financial-services": [
        "Portfolio Manager", "Risk Analyst", "Compliance Officer", "Trader",
        "Wealth Advisor", "Credit Analyst", "Quantitative Analyst", "Auditor",
    ],
    "gaming": [
        "Game Designer", "Community Manager", "QA Tester", "Server Admin",
        "LiveOps Engineer", "Esports Coordinator", "Balance Designer", "Producer",
    ],
    "software-engineering": [
        "Staff Engineer", "SRE", "DevOps Engineer", "Security Engineer",
        "Platform Engineer", "Tech Lead", "Engineering Manager", "Principal Architect",
    ],
    "conservation": [
        "Field Researcher", "Park Ranger", "Wildlife Veterinarian", "GIS Analyst",
        "Conservation Officer", "Marine Biologist", "Ecologist", "Policy Advisor",
    ],
    "data-journalism": [
        "Senior Reporter", "Data Editor", "Investigative Journalist", "Fact-Checker",
        "Graphics Editor", "FOIA Specialist", "Copy Editor", "Bureau Chief",
    ],
}


# ---------------------------------------------------------------------------
# Value generators
# ---------------------------------------------------------------------------


def generate_email(name: str) -> str:
    """Generate a realistic email from a person name."""
    parts = name.lower().split()
    first = parts[0].replace("'", "")
    last = parts[-1].replace("'", "")
    domains = ["example.com", "company.org", "acme.co", "corp.net"]
    return f"{first}.{last}@{random.choice(domains)}"


def generate_phone() -> str:
    """Generate a realistic US phone number."""
    area = random.randint(200, 999)
    prefix = random.randint(200, 999)
    line = random.randint(1000, 9999)
    return f"+1-{area}-{prefix}-{line}"


def generate_date(start_year: int = 2024, end_year: int = 2026) -> str:
    """Generate a random date string in ISO format."""
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    random_date = start + timedelta(days=random.randint(0, delta))
    return random_date.isoformat()


def generate_datetime(start_year: int = 2024, end_year: int = 2026) -> str:
    """Generate a random datetime string in ISO format."""
    d = generate_date(start_year, end_year)
    hour = random.randint(8, 17)
    minute = random.choice([0, 15, 30, 45])
    return f"{d}T{hour:02d}:{minute:02d}:00"


def generate_id(prefix: str, index: int) -> str:
    """Generate a realistic ID string."""
    year = random.choice([2024, 2025, 2026])
    return f"{prefix.upper()}-{year}-{index:04d}"


def generate_currency(min_val: float = 100, max_val: float = 500000) -> float:
    """Generate a realistic currency amount."""
    return round(random.uniform(min_val, max_val), 2)


def generate_url(name: str) -> str:
    """Generate a URL from a name."""
    slug = name.lower().replace(" ", "-").replace("'", "")
    return f"https://www.{slug}.example.com"


def generate_address() -> str:
    """Generate a realistic address."""
    return f"{random.choice(_STREETS)}, {random.choice(_CITIES)}"


def generate_latitude() -> float:
    """Generate a realistic latitude."""
    return round(random.uniform(25.0, 48.0), 6)


def generate_longitude() -> float:
    """Generate a realistic longitude."""
    return round(random.uniform(-122.0, -71.0), 6)


# ---------------------------------------------------------------------------
# Main interface
# ---------------------------------------------------------------------------


def get_names_for_pole_type(
    pole_type: str, count: int, *, domain_id: str | None = None,
) -> list[str]:
    """Get realistic names appropriate for the given POLE+O type.

    If *domain_id* is provided, domain-specific pools are checked first so that
    base entities use contextually appropriate names (e.g. doctors for healthcare).
    """
    # Try domain-specific base pools first
    domain_pools: dict[str, dict[str, list[str]]] = {
        "PERSON": DOMAIN_PERSON_NAMES,
        "ORGANIZATION": DOMAIN_ORGANIZATION_NAMES,
        "LOCATION": DOMAIN_LOCATION_NAMES,
        "EVENT": DOMAIN_EVENT_NAMES,
        "OBJECT": DOMAIN_OBJECT_NAMES,
    }
    pool = None
    if domain_id:
        dp = domain_pools.get(pole_type.upper())
        if dp and domain_id in dp:
            pool = dp[domain_id]

    if pool is None:
        pool = {
            "PERSON": PERSON_NAMES,
            "ORGANIZATION": ORGANIZATION_NAMES,
            "LOCATION": LOCATION_NAMES,
            "EVENT": EVENT_NAMES,
            "OBJECT": OBJECT_NAMES,
        }.get(pole_type.upper(), OBJECT_NAMES)

    # Extend pool if more names needed than available
    names = list(pool)
    while len(names) < count:
        names.extend(f"{n} {chr(65 + i)}" for i, n in enumerate(pool))
    return names[:count]


def get_names_for_label(
    label: str, pole_type: str, count: int, *, domain_id: str | None = None,
) -> list[str]:
    """Get names appropriate for a specific entity label.

    Checks the domain-specific ``LABEL_NAMES`` pool first, then falls back to
    the generic POLE+O pool via ``get_names_for_pole_type``.
    """
    if label in LABEL_NAMES:
        pool = LABEL_NAMES[label]
        names = list(pool)
        # Extend if more names needed than available
        suffix = 0
        while len(names) < count:
            suffix += 1
            names.extend(f"{n} {suffix}" for n in pool)
        return names[:count]
    return get_names_for_pole_type(pole_type, count, domain_id=domain_id)


_PERSON_LABELS = {
    "Person", "Patient", "Provider", "Player", "Journalist", "Source",
    "Agent", "Contributor", "Character", "Traveler", "Suspect", "Witness",
    "Developer", "Researcher", "Scientist", "Engineer", "Officer", "Ranger",
    "Worker", "Employee", "Instructor", "Advisor", "Analyst", "Athlete",
    "Artist", "Author", "Musician", "Director", "Manager", "Coordinator",
}

_ORGANIZATION_LABELS = {
    "Organization", "Hospital", "Facility", "Company", "Guild", "Publisher",
    "Agency", "Department", "School", "University", "Institute", "Clinic",
    "Studio", "Team", "Corporation", "Foundation", "Association", "Lab",
    "Bureau", "Firm", "Outlet", "Network", "Platform", "Exchange",
    "Institution", "Resort",
}

_LOCATION_LABELS = {
    "Location", "Site", "Address", "Region", "Warehouse", "Store", "Airport",
    "Port", "Field", "Venue", "Neighborhood", "Boundary", "Coordinate",
    "Destination", "Course", "Habitat", "Room", "Well", "Formation",
}

_EVENT_LABELS = {
    "Event", "Incident", "Inspection", "Appointment", "Transaction", "Sprint",
    "Deployment", "Match", "Session", "Round", "Tournament", "Sighting",
    "Encounter", "Experiment", "Evaluation", "Survey", "Booking", "Reservation",
    "Conversation", "Alert", "Correction",
}

_OBJECT_LABELS = {
    "Object", "Medication", "Asset", "Product", "Contract", "Report", "Order",
    "Document", "Claim", "Policy", "Equipment", "Sensor", "Camera", "System",
    "Model", "Prompt", "Paper", "Grant", "Permit", "Package", "Layer",
    "MapProject", "Feature", "Note", "Bookmark", "JournalEntry", "Topic",
    "Project", "Campaign", "Category", "Epic", "Metric", "Objective",
    "Release", "Feedback", "Reading", "MaintenanceRecord", "ToolCall",
    "Memory", "Entity", "Handicap", "Hole", "Threat",
}

# Label-specific description overrides for more natural descriptions
_LABEL_DESCRIPTION_OVERRIDES: dict[str, list[str]] = {
    "Medication": [
        "Prescribed medication {name} used in clinical treatment protocols.",
        "{name}, a pharmaceutical agent administered under clinical supervision.",
        "Medication {name} — part of the treatment regimen for patient care.",
    ],
    "Permit": [
        "Regulatory permit {name} issued for authorized operations.",
        "{name}, a compliance document authorizing specific field activities.",
        "Permit {name} — required authorization for operational activities.",
    ],
    "Sensor": [
        "{name}, an instrumentation device capturing real-time measurements.",
        "Monitoring sensor {name} providing continuous operational data.",
        "{name} — deployed sensor feeding data to the monitoring network.",
    ],
    "Equipment": [
        "{name}, industrial equipment maintained per operational schedules.",
        "Field equipment {name} essential for daily operations.",
        "{name} — key piece of operational machinery under active maintenance.",
    ],
    "Paper": [
        "Research publication: {name}.",
        "{name} — peer-reviewed study contributing to the field.",
        "Academic paper: {name}, published in a leading journal.",
    ],
    "Model": [
        "{name}, a machine learning model deployed for inference workloads.",
        "AI model {name} — trained and evaluated for production use.",
        "{name} — language model serving requests in the inference pipeline.",
    ],
    "Species": [
        "{name}, a species tracked across habitats and conservation zones.",
        "Monitored species: {name}, part of ongoing conservation programs.",
        "{name} — tracked species with population assessments and field observations.",
    ],
}


def _generate_description(
    label: str, entity_name: str, domain_id: str | None, index: int
) -> str:
    """Generate a realistic description based on entity label and domain."""
    domain_display = (domain_id or "general").replace("-", " ")

    if label in _PERSON_LABELS:
        roles = DOMAIN_ROLE_POOL.get(domain_id, _ROLE_POOL) if domain_id else _ROLE_POOL
        role = roles[index % len(roles)]
        templates = [
            f"{entity_name}, {role.lower()} specializing in {domain_display}.",
            f"{role} {entity_name} — active in the {domain_display} sector with relevant domain expertise.",
            f"{entity_name} serves as {role.lower()}, contributing to {domain_display} initiatives and operations.",
        ]
        return templates[index % len(templates)]

    if label in _ORGANIZATION_LABELS:
        pool = DOMAIN_INDUSTRY_POOL.get(domain_id, _INDUSTRY_POOL) if domain_id else _INDUSTRY_POOL
        industry = pool[index % len(pool)]
        templates = [
            f"{entity_name} is a {industry.lower()} organization operating in the {domain_display} space.",
            f"{industry} entity {entity_name}, providing services and resources for {domain_display} operations.",
            f"{entity_name} — a {industry.lower()} institution active in {domain_display}.",
        ]
        return templates[index % len(templates)]

    # Check label-specific overrides first
    if label in _LABEL_DESCRIPTION_OVERRIDES:
        templates = _LABEL_DESCRIPTION_OVERRIDES[label]
        return templates[index % len(templates)].format(name=entity_name)

    if label in _LOCATION_LABELS:
        templates = [
            f"{entity_name}, a {label.lower()} in the {domain_display} region.",
            f"{label} {entity_name} — a key site for {domain_display} activities.",
            f"{entity_name} serves as an important {label.lower()} within {domain_display} operations.",
        ]
        return templates[index % len(templates)]

    if label in _EVENT_LABELS:
        templates = [
            f"{entity_name}, a {label.lower()} event recorded in the {domain_display} timeline.",
            f"{label} {entity_name} — occurred as part of {domain_display} activities.",
            f"Recorded {label.lower()}: {entity_name}, relevant to {domain_display} workflows.",
        ]
        return templates[index % len(templates)]

    if label in _OBJECT_LABELS:
        templates = [
            f"{entity_name}, a {label.lower()} used in {domain_display} workflows.",
            f"{label} {entity_name} — cataloged for {domain_display} operations.",
            f"{entity_name} is a {label.lower()} supporting {domain_display} processes.",
        ]
        return templates[index % len(templates)]

    # Fallback for any remaining labels
    templates = [
        f"{entity_name}, a {label.lower()} relevant to {domain_display} operations.",
        f"{label} {entity_name} — part of the {domain_display} knowledge graph.",
        f"{entity_name} is a {label.lower()} tracked within the {domain_display} domain.",
    ]
    return templates[index % len(templates)]


def generate_property_value(
    prop_name: str,
    prop_type: str,
    entity_name: str,
    label: str,
    index: int,
    *,
    domain_id: str | None = None,
) -> str | int | float | bool | None:
    """Generate a contextually appropriate property value based on name and type."""
    name_lower = prop_name.lower()

    # Handle by property name patterns first
    if name_lower in _EMAIL_PROPERTIES:
        return generate_email(entity_name)
    if name_lower in _PHONE_PROPERTIES:
        return generate_phone()
    if name_lower in _URL_PROPERTIES:
        return generate_url(entity_name)
    if name_lower in _ADDRESS_PROPERTIES:
        return generate_address()
    if name_lower == "role" or name_lower == "title":
        # Use domain-specific roles if available
        pool = DOMAIN_ROLE_POOL.get(domain_id, _ROLE_POOL) if domain_id else _ROLE_POOL
        return pool[index % len(pool)]
    if name_lower == "industry":
        pool = DOMAIN_INDUSTRY_POOL.get(domain_id, _INDUSTRY_POOL) if domain_id else _INDUSTRY_POOL
        return pool[index % len(pool)]
    if name_lower == "latitude" or name_lower == "lat":
        return generate_latitude()
    if name_lower == "longitude" or name_lower in ("lon", "lng"):
        return generate_longitude()
    if name_lower == "currency":
        return _CURRENCY_POOL[index % len(_CURRENCY_POOL)]
    if name_lower in ("ticker", "symbol", "stock_symbol"):
        return _TICKER_POOL[index % len(_TICKER_POOL)]
    if name_lower == "drug_class":
        return _DRUG_CLASS_POOL[index % len(_DRUG_CLASS_POOL)]
    if name_lower == "scientific_name":
        return entity_name
    if name_lower == "status":
        return _STATUS_POOL[index % len(_STATUS_POOL)]
    if name_lower in ("severity", "priority"):
        return _SEVERITY_POOL[index % len(_SEVERITY_POOL)]
    if name_lower in ("language", "primary_language"):
        return _LANGUAGE_POOL[index % len(_LANGUAGE_POOL)]
    if name_lower in ("country", "nationality", "country_of_origin"):
        return _COUNTRY_POOL[index % len(_COUNTRY_POOL)]
    if name_lower in ("gender", "sex"):
        return random.choice(["Male", "Female", "Non-binary"])
    if name_lower == "blood_type":
        return random.choice(["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"])
    if name_lower in ("chief_complaint", "complaint"):
        return _COMPLAINT_POOL[index % len(_COMPLAINT_POOL)]
    if name_lower == "disposition":
        return _DISPOSITION_POOL[index % len(_DISPOSITION_POOL)]
    if name_lower in ("specialty", "specialization"):
        return _SPECIALTY_POOL[index % len(_SPECIALTY_POOL)]
    if name_lower in ("contraindications", "contraindication"):
        return _CONTRAINDICATION_POOL[index % len(_CONTRAINDICATION_POOL)]
    if name_lower in ("dosage_form", "form", "formulation"):
        return _DOSAGE_FORM_POOL[index % len(_DOSAGE_FORM_POOL)]
    if name_lower in ("allergies", "allergy", "known_allergies"):
        return _ALLERGY_POOL[index % len(_ALLERGY_POOL)]
    if name_lower in ("sector", "market_sector", "industry_sector"):
        return _SECTOR_POOL[index % len(_SECTOR_POOL)]
    if name_lower in ("lead_reporter", "lead_journalist", "reporter", "journalist", "author"):
        return _REPORTER_POOL[index % len(_REPORTER_POOL)]
    if name_lower in ("manufacturer", "supplier", "vendor"):
        return ORGANIZATION_NAMES[index % len(ORGANIZATION_NAMES)]
    if name_lower in ("mechanism_of_action", "mechanism"):
        mechanisms = [
            "Inhibits HMG-CoA reductase", "Blocks angiotensin II receptors",
            "Selective serotonin reuptake inhibition", "Beta-adrenergic blockade",
            "Reduces hepatic glucose production", "Calcium channel blockade",
        ]
        return mechanisms[index % len(mechanisms)]
    if name_lower in ("population_trend",):
        return random.choice(["increasing", "stable", "decreasing", "unknown"])
    if name_lower in ("habitat", "primary_habitat"):
        habitats = [
            "Tropical rainforest", "Savanna grassland", "Temperate deciduous forest",
            "Coral reef", "Arctic tundra", "Mangrove wetland",
        ]
        return habitats[index % len(habitats)]

    # Handle by type
    if prop_type in ("string", "str"):
        if name_lower in _DESCRIPTION_PROPERTIES:
            return _generate_description(label, entity_name, domain_id, index)
        if any(id_word in name_lower for id_word in ("_id", "code", "number", "identifier")):
            prefix = LABEL_ID_PREFIXES.get(label, label[:3].upper())
            return generate_id(prefix, index)
        # Return entity_name for name-like fields, or a contextual value
        if "name" in name_lower or "label" in name_lower:
            return entity_name
        return f"{entity_name} - {prop_name.replace('_', ' ').title()}"
    if prop_type in ("integer", "int"):
        if "count" in name_lower or "quantity" in name_lower:
            return random.randint(1, 100)
        if "year" in name_lower:
            return random.choice([2023, 2024, 2025, 2026])
        if "age" in name_lower:
            return random.randint(18, 75)
        if "size" in name_lower:
            return random.randint(100, 1000000)
        if "score" in name_lower or "rating" in name_lower:
            return random.randint(1, 100)
        return random.randint(10, 10000)
    if prop_type == "float":
        if "price" in name_lower or "cost" in name_lower or "amount" in name_lower or "balance" in name_lower:
            return generate_currency()
        if "weight" in name_lower:
            return round(random.uniform(0.5, 500.0), 2)
        if "rate" in name_lower or "percentage" in name_lower:
            return round(random.uniform(0.01, 0.99), 4)
        if "confidence" in name_lower or "score" in name_lower or "rating" in name_lower:
            return round(random.uniform(0.5, 1.0), 2)
        if "efficiency" in name_lower or "accuracy" in name_lower or "utilization" in name_lower:
            return round(random.uniform(60.0, 99.0), 1)
        return round(random.uniform(1.0, 1000.0), 2)
    if prop_type in ("boolean", "bool"):
        return random.choice([True, False])
    if prop_type == "date":
        return generate_date()
    if prop_type == "datetime":
        return generate_datetime()
    if prop_type == "point":
        return f"POINT({generate_longitude()} {generate_latitude()})"

    return f"{entity_name} {prop_name}"
