"""Name / place / medical pools for the synthetic generator.

SEEN pools are what we look at while building detectors. HELDOUT pools are never put in
a detector gazetteer (tests/test_synth.py asserts this) and are used for the held-out
split. All people are fictional.
"""
from __future__ import annotations

# (latin, devanagari)
FIRST_M_SEEN = [
    ("Rajesh", "राजेश"), ("Suresh", "सुरेश"), ("Mahesh", "महेश"), ("Ramesh", "रमेश"), ("Dinesh", "दिनेश"),
    ("Mukesh", "मुकेश"), ("Anil", "अनिल"), ("Sunil", "सुनील"), ("Vijay", "विजय"), ("Ajay", "अजय"),
    ("Sanjay", "संजय"), ("Manoj", "मनोज"), ("Rakesh", "राकेश"), ("Deepak", "दीपक"), ("Vikas", "विकास"),
    ("Amit", "अमित"), ("Rohit", "रोहित"), ("Ashok", "अशोक"), ("Prakash", "प्रकाश"), ("Naresh", "नरेश"),
    ("Pankaj", "पंकज"), ("Sandeep", "संदीप"), ("Arun", "अरुण"), ("Vinod", "विनोद"), ("Santosh", "संतोष"),
    ("Rahul", "राहुल"), ("Gopal", "गोपाल"), ("Ravi", "रवि"), ("Nitin", "नितिन"), ("Alok", "आलोक"),
    ("Mohammad", "मोहम्मद"), ("Imran", "इमरान"), ("Salman", "सलमान"), ("Irfan", "इरफान"), ("Rashid", "राशिद"),
    ("Gurpreet", "गुरप्रीत"), ("Harpreet", "हरप्रीत"), ("Venkatesh", "वेंकटेश"), ("Shyam", "श्याम"), ("Krishna", "कृष्णा"),
]
FIRST_M_HELD = [
    ("Chandrakant", "चंद्रकांत"), ("Dharmendra", "धर्मेंद्र"), ("Eknath", "एकनाथ"), ("Gajanan", "गजानन"),
    ("Jagdish", "जगदीश"), ("Kailash", "कैलाश"), ("Lalit", "ललित"), ("Madhav", "माधव"), ("Nilesh", "नीलेश"),
    ("Omkar", "ओंकार"), ("Pramod", "प्रमोद"), ("Raghunath", "रघुनाथ"), ("Satish", "सतीश"), ("Umesh", "उमेश"),
    ("Vishwanath", "विश्वनाथ"), ("Yashwant", "यशवंत"), ("Aftab", "आफताब"), ("Bilal", "बिलाल"),
    ("Danish", "दानिश"), ("Ehsan", "एहसान"), ("Tushar", "तुषार"), ("Bhaskar", "भास्कर"),
]
FIRST_F_SEEN = [
    ("Sunita", "सुनीता"), ("Anita", "अनीता"), ("Kavita", "कविता"), ("Savita", "सविता"), ("Sangeeta", "संगीता"),
    ("Geeta", "गीता"), ("Seema", "सीमा"), ("Reena", "रीना"), ("Meena", "मीना"), ("Neha", "नेहा"),
    ("Pooja", "पूजा"), ("Priya", "प्रिया"), ("Rekha", "रेखा"), ("Sarita", "सरिता"), ("Usha", "उषा"),
    ("Asha", "आशा"), ("Mamta", "ममता"), ("Rani", "रानी"), ("Kamla", "कमला"), ("Sushila", "सुशीला"),
    ("Radha", "राधा"), ("Sita", "सीता"), ("Lakshmi", "लक्ष्मी"), ("Poonam", "पूनम"), ("Rashmi", "रश्मि"),
    ("Anjali", "अंजलि"), ("Nisha", "निशा"), ("Jyoti", "ज्योति"), ("Kiran", "किरण"), ("Manju", "मंजू"),
    ("Fatima", "फातिमा"), ("Ayesha", "आयशा"), ("Shabnam", "शबनम"), ("Simran", "सिमरन"), ("Shanti", "शांति"),
]
FIRST_F_HELD = [
    ("Chandni", "चांदनी"), ("Dhanashree", "धनश्री"), ("Gayatri", "गायत्री"), ("Hemlata", "हेमलता"),
    ("Jaya", "जया"), ("Kalpana", "कल्पना"), ("Leela", "लीला"), ("Madhuri", "माधुरी"), ("Nirmala", "निर्मला"),
    ("Padma", "पद्मा"), ("Radhika", "राधिका"), ("Sulochana", "सुलोचना"), ("Tabassum", "तबस्सुम"),
    ("Urmila", "उर्मिला"), ("Vandana", "वंदना"), ("Yamini", "यामिनी"), ("Zeenat", "ज़ीनत"), ("Parveen", "परवीन"),
]
LAST_SEEN = [
    ("Kumar", "कुमार"), ("Sharma", "शर्मा"), ("Verma", "वर्मा"), ("Gupta", "गुप्ता"), ("Singh", "सिंह"),
    ("Yadav", "यादव"), ("Mishra", "मिश्रा"), ("Pandey", "पांडेय"), ("Tiwari", "तिवारी"), ("Dubey", "दुबे"),
    ("Shukla", "शुक्ला"), ("Srivastava", "श्रीवास्तव"), ("Agarwal", "अग्रवाल"), ("Jain", "जैन"), ("Patel", "पटेल"),
    ("Mehta", "मेहता"), ("Joshi", "जोशी"), ("Chauhan", "चौहान"), ("Thakur", "ठाकुर"), ("Saxena", "सक्सेना"),
    ("Kapoor", "कपूर"), ("Reddy", "रेड्डी"), ("Nair", "नायर"), ("Khan", "खान"), ("Ansari", "अंसारी"),
    ("Siddiqui", "सिद्दीकी"), ("Chaudhary", "चौधरी"), ("Bansal", "बंसल"), ("Das", "दास"), ("Ghosh", "घोष"),
]
LAST_HELD = [
    ("Bhosale", "भोसले"), ("Deshmukh", "देशमुख"), ("Gaikwad", "गायकवाड"), ("Hegde", "हेगड़े"),
    ("Kulkarni", "कुलकर्णी"), ("Naidu", "नायडू"), ("Pillai", "पिल्लई"), ("Shetty", "शेट्टी"),
    ("Trivedi", "त्रिवेदी"), ("Upadhyay", "उपाध्याय"), ("Vaidya", "वैद्य"), ("Zaidi", "ज़ैदी"),
    ("Mirza", "मिर्ज़ा"), ("Lodhi", "लोधी"), ("Nishad", "निषाद"), ("Baghel", "बघेल"), ("Tomar", "तोमर"),
    ("Sahu", "साहू"), ("Rastogi", "रस्तोगी"), ("Awasthi", "अवस्थी"),
]
# patronymic first names used for fathers / husbands (both splits draw from the split's pool)
FATHER_EXTRA_SEEN = [("Shyam Lal", "श्याम लाल"), ("Ram Prasad", "राम प्रसाद"), ("Hari Om", "हरि ओम")]
FATHER_EXTRA_HELD = [("Banwari Lal", "बनवारी लाल"), ("Chhotey Lal", "छोटे लाल"), ("Mool Chand", "मूल चंद")]

# (latin, devanagari)
CITIES_SEEN = [
    ("Lucknow", "लखनऊ"), ("Kanpur", "कानपुर"), ("Patna", "पटना"), ("Jaipur", "जयपुर"), ("Indore", "इंदौर"),
    ("Bhopal", "भोपाल"), ("Varanasi", "वाराणसी"), ("Agra", "आगरा"), ("Nagpur", "नागपुर"), ("Delhi", "दिल्ली"),
    ("Meerut", "मेरठ"), ("Ranchi", "रांची"),
]
CITIES_HELD = [
    ("Gorakhpur", "गोरखपुर"), ("Jhansi", "झांसी"), ("Bareilly", "बरेली"), ("Aligarh", "अलीगढ़"),
    ("Raipur", "रायपुर"), ("Gwalior", "ग्वालियर"), ("Muzaffarpur", "मुजफ्फरपुर"), ("Dhanbad", "धनबाद"),
]
AREA_WORDS_SEEN = [
    ("Gandhi", "गांधी"), ("Nehru", "नेहरू"), ("Shastri", "शास्त्री"), ("Ambedkar", "अंबेडकर"),
    ("Subhash", "सुभाष"), ("Rajiv", "राजीव"), ("Laxmi", "लक्ष्मी"), ("Shiv", "शिव"), ("Azad", "आज़ाद"),
]
AREA_WORDS_HELD = [
    ("Tilak", "तिलक"), ("Patel", "पटेल"), ("Vivekanand", "विवेकानंद"), ("Kabir", "कबीर"),
    ("Ashok", "अशोक"), ("Sardar", "सरदार"), ("Bhagat", "भगत"),
]
AREA_SUFFIX = [
    ("Nagar", "नगर"), ("Colony", "कॉलोनी"), ("Vihar", "विहार"), ("Road", "रोड"), ("Marg", "मार्ग"),
    ("Chowk", "चौक"), ("Enclave", "एन्क्लेव"), ("Puram", "पुरम"), ("Ganj", "गंज"),
]
LANDMARKS = [  # (latin, devanagari)
    ("Hanuman mandir", "हनुमान मंदिर"), ("Sai Baba mandir", "साईं बाबा मंदिर"), ("Jama Masjid", "जामा मस्जिद"),
    ("SBI bank", "एसबीआई बैंक"), ("Govt School", "सरकारी स्कूल"), ("bus stand", "बस स्टैंड"),
    ("water tank", "पानी की टंकी"), ("Gurudwara", "गुरुद्वारा"), ("railway station", "रेलवे स्टेशन"),
    ("Shiv mandir", "शिव मंदिर"), ("petrol pump", "पेट्रोल पंप"), ("post office", "डाक घर"),
]

# ---------------------------------------------------------------- medical content
DIAGNOSES = [  # (english, hinglish, hindi)
    ("Dengue fever", "dengue bukhar", "डेंगू बुखार"),
    ("Typhoid fever", "typhoid", "टायफाइड"),
    ("Malaria", "malaria", "मलेरिया"),
    ("Community acquired pneumonia", "pneumonia", "निमोनिया"),
    ("Acute gastroenteritis", "gastro (dast ulti)", "तीव्र गैस्ट्रोएंटेराइटिस"),
    ("Type 2 diabetes mellitus", "sugar ki bimari (diabetes)", "मधुमेह"),
    ("Hypertension", "high BP", "उच्च रक्तचाप"),
    ("Acute kidney injury", "kidney failure (AKI)", "तीव्र गुर्दा क्षति"),
    ("Urinary tract infection", "urine infection (UTI)", "मूत्र मार्ग संक्रमण"),
    ("Bronchial asthma", "dama (asthma)", "दमा"),
    ("Iron deficiency anemia", "khoon ki kami (anemia)", "एनीमिया"),
    ("Acute appendicitis", "appendicitis", "एपेंडिसाइटिस"),
    ("Fracture neck of femur", "kulhe ki haddi toota", "जांघ की हड्डी का फ्रैक्चर"),
    ("Acute myocardial infarction", "heart attack (MI)", "हृदयाघात"),
    ("Chikungunya", "chikungunya", "चिकनगुनिया"),
    ("Pulmonary tuberculosis", "TB (tuberculosis)", "क्षय रोग"),
    ("Viral hepatitis A", "jaundice (peeliya)", "पीलिया"),
    ("Cellulitis left leg", "pair mein infection", "पैर में संक्रमण"),
    ("Cholelithiasis", "pitt ki pathri", "पित्त की पथरी"),
    ("Snake bite", "saanp ka katna", "सांप का काटना"),
]
RARE_DIAGNOSES = [
    ("Guillain-Barre syndrome", "GBS", "गुइलेन-बैरे सिंड्रोम"),
    ("Wilson disease", "Wilson disease", "विल्सन रोग"),
    ("Kala-azar (visceral leishmaniasis)", "kala-azar", "कालाजार"),
    ("Neurocysticercosis", "neurocysticercosis", "न्यूरोसिस्टिसर्कोसिस"),
    ("Takayasu arteritis", "Takayasu arteritis", "ताकायासु आर्टराइटिस"),
]
PROCEDURES = ["Appendicectomy", "Cholecystectomy", "Hemiarthroplasty", "Coronary angioplasty", "Hernioplasty",
              "Incision and drainage", "Blood transfusion 2 units", "Hemodialysis session"]
DRUGS = [  # (name with strength as written, route prefix)
    ("Dolo 650", "Tab."), ("Paracetamol 500 mg", "Tab."), ("Crocin 650", "Tab."), ("Azithromycin 500 mg", "Tab."),
    ("Amoxicillin 500 mg", "Cap."), ("Augmentin 625", "Tab."), ("Pantoprazole 40 mg", "Tab."), ("Pan 40", "Tab."),
    ("Ondansetron 4 mg", "Tab."), ("Metformin 500 mg", "Tab."), ("Glimepiride 1 mg", "Tab."),
    ("Amlodipine 5 mg", "Tab."), ("Telmisartan 40 mg", "Tab."), ("Atorvastatin 20 mg", "Tab."),
    ("Ecosprin 75 mg", "Tab."), ("Clopidogrel 75 mg", "Tab."), ("Cefixime 200 mg", "Tab."),
    ("Ceftriaxone 1 g", "Inj."), ("Metronidazole 400 mg", "Tab."), ("Ciplox 500", "Tab."),
    ("Levocetirizine 5 mg", "Tab."), ("Montair LC", "Tab."), ("Ascoril LS", "Syp."), ("Becosules", "Cap."),
    ("Shelcal 500", "Tab."), ("Zerodol SP", "Tab."), ("Meftal Spas", "Tab."), ("Cyclopam", "Tab."),
    ("Insulin Mixtard 30/70", "Inj."), ("Furosemide 40 mg", "Inj."), ("ORS", "Sachet"), ("Zincovit", "Tab."),
]
FREQS = ["OD", "BD", "TDS", "QID", "HS", "SOS", "1-0-1", "1-1-1", "0-0-1", "1-0-0"]
LABS = [  # name, lo, hi, decimals, unit
    ("Hb", 6.0, 15.5, 1, "g/dL"), ("WBC", 3500, 18000, 0, "/cumm"), ("Platelets", 20000, 400000, 0, "/cumm"),
    ("Creatinine", 0.5, 4.5, 1, "mg/dL"), ("Urea", 15, 120, 0, "mg/dL"), ("RBS", 70, 420, 0, "mg/dL"),
    ("Na", 125, 148, 0, "mEq/L"), ("K", 3.0, 5.8, 1, "mEq/L"), ("CRP", 2, 180, 0, "mg/L"),
    ("ALT", 15, 400, 0, "U/L"), ("HbA1c", 5.2, 12.0, 1, "%"),
]
HOSPITAL_DEPTS = ["Medicine", "Surgery", "Pediatrics", "Orthopedics", "Gynecology", "ICU", "Cardiology"]
DOCTOR_FIRST_INITIALS = "ABCDGHJKMNPRSTV"

HI_MONTHS = ["जनवरी", "फरवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]
EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]

# names used ONLY for canaries (drawn from held-out pools so no gazetteer covers them)
CANARY_FIRST = ["Tejaswi", "Ibrahim", "Narayan", "Girija", "Harsha", "Sumedh", "Farhan", "Meghna", "Kunal", "Ishwar"]
CANARY_LAST = ["Karnik", "Bhandari", "Sabharwal", "Mukherjee", "Fernandes", "Thapliyal", "Chettiar", "Dalvi"]
