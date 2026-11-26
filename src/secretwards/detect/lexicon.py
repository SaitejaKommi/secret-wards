"""Word lists used to veto false name/address hits and to protect medical text.

Three tiers:
  DRUG_WORDS      hard veto: a drug is never a person ("Dr. Paracetamol")
  CLINICAL_WORDS  diseases, anatomy, units, document labels: veto unless a strong label cue
  COMMON_WORDS    English / Hinglish function words
General-language knowledge, not derived from our synthetic data.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..normalize.translit import skeleton

_DATA = Path(__file__).parent / "gazetteer" / "data"


def _words(s: str) -> frozenset[str]:
    return frozenset(w for w in s.lower().split() if w)


DRUG_WORDS = _words("""
paracetamol dolo crocin calpol acetaminophen ibuprofen brufen combiflam diclofenac voveran aspirin ecosprin
amoxicillin augmentin amoxyclav azithromycin azee zithromax cefixime ceftriaxone cefuroxime cefpodoxime taxim zifi
ciprofloxacin ciplox levofloxacin norfloxacin ofloxacin doxycycline metronidazole flagyl tinidazole
pantoprazole pan pantop omeprazole rabeprazole esomeprazole ranitidine famotidine ondansetron ondem domperidone
metformin glimepiride gliclazide insulin mixtard lantus amlodipine telmisartan losartan atenolol metoprolol
atorvastatin rosuvastatin clopidogrel furosemide lasix spironolactone salbutamol budesonide montelukast montair
levocetirizine cetirizine fexofenadine prednisolone dexamethasone hydrocortisone heparin enoxaparin warfarin
artemether chloroquine primaquine ors zinc zincovit becosules shelcal calcium folic iron vitamin ascoril cyclopam
zerodol meftal mefenamic nimesulide tramadol pregabalin gabapentin levetiracetam phenytoin diazepam lorazepam
alprazolam sertraline escitalopram ranitidine ciplox monocef sinarest cetrizine volini moov saline ringer
dettol betadine soframycin neosporin amikacin gentamicin vancomycin meropenem piperacillin linezolid colistin
tab cap inj syp syr oint susp drops sachet tablet capsule injection syrup
""")
CLINICAL_WORDS = _words("""
fever cough cold pain headache vomiting nausea diarrhea diarrhoea weakness fatigue dizziness breathlessness
dyspnea chest abdomen abdominal stomach liver kidney heart lung lungs brain blood urine stool sputum pulse
bp hr rr spo2 temp temperature pressure sugar glucose rbs fbs ppbs hba1c hb hemoglobin haemoglobin wbc rbc tlc
platelet platelets plt creatinine urea bilirubin alt ast sgpt sgot na k crp esr tsh cholesterol hdl ldl
dengue typhoid malaria pneumonia gastroenteritis diabetes mellitus hypertension injury infection tract
asthma bronchial anemia anaemia appendicitis fracture femur neck myocardial infarction chikungunya
pulmonary tuberculosis tb hepatitis jaundice cellulitis cholelithiasis snake bite sepsis stroke failure
renal acute chronic viral bacterial syndrome disease deficiency iron guillain barre wilson kala azar
neurocysticercosis takayasu arteritis left right leg arm hand foot knee hip shoulder spine head
appendicectomy cholecystectomy hemiarthroplasty angioplasty hernioplasty incision drainage transfusion
hemodialysis dialysis surgery operation procedure biopsy scan xray ct mri ecg echo ultrasound usg
mg ml mcg gm kg cm mm hg mmhg dl cumm iu units meq bpm min days day weeks week months month years year yrs
od bd bid tds tid qid hs sos prn stat ac pc daily twice thrice once
patient pt attendant relative diagnosis dx rx treatment advice investigations vitals complaints history
examination admission admitted discharge discharged summary report referral referred follow review opd ipd
icu ward bed hospital clinic medical department dept ot lab laboratory pathology radiology pharmacy
male female sex age aged dob address phone mobile contact email policy insurance claim member uhid mrn reg
registration number no name guardian husband wife father mother son daughter brother sister uncle aunty
total normal abnormal positive negative high low mild moderate severe stable critical improved
tablet capsule injection syrup ointment cream drops inhaler nebulization iv im sc po oral topical
left right bilateral both upper lower anterior posterior sample collected results result test tests
ok oral note notes remarks comments final principal primary secondary other others none nil
medicine medicines neurology cardiology nephrology urology gastroenterology pulmonology orthopaedics orthopedics paediatrics pediatrics
gynaecology gynecology obstetrics ophthalmology dermatology psychiatry oncology radiology anaesthesia anesthesia emergency casualty
outpatient inpatient speciality specialty consultant resident intern
serum plasma sodium potassium calcium chloride magnesium phosphorus albumin globulin protein hemogram haemogram lipid profile thyroid
liver function kidney electrolytes culture widal differential count total fasting random postprandial
htn dm dm2 t2dm t1dm ckd cad cva ihd copd bph uti urti lrti pcos gerd ra oa sle ards aki hiv hbv hcv ecg ncv eeg
glucometer strips pharmacy counter reddy's morepen reddys id abha uhid sample superintendent director medical referral
referred sincerely regards pathology specimen collected claim member hospital principal correspondence
""")
COMMON_WORDS = _words("""
a an the and or but if then else so as at by for from in into of on onto to with without within about above
after again against all also am any are aren't be because been before being below between both can could did
do does doing down during each few further had has have having he her here hers herself him himself his how
i is it its itself just me more most my myself no nor not now off once only other our ours out over own same
she should some such than that their theirs them themselves there these they this those through too under until
up very was we were what when where which while who whom why will would you your yours yourself
please kindly sir madam dear regards sincerely yours thanks thank report sent send bhej raha hu hain hai ho hoga
ka ki ke ko ne se me mein par pe aur ya bhi tha thi the toh to nahi nahin kya kab kaise kyun yahan wahan ye wo
mera meri mere aapka aapki aapke hum hamara hamari tum tumhara unka unki unke inka inki inke apna apni apne
call karo kar karna kijiye dena dijiye liya diya gaya gayi gaye aaya aayi aaye rehte rehta rehti bataya bata
ghar gaon shehar mohalla pata mobile phone number naam umar saal din raat subah shaam dawai dawa goli
mareez mareez rogi bimari bukhar khansi dard pet sar seene kamzori ulti dast ji haan ha ok okay
date time am pm today tomorrow yesterday week month year morning evening night
first second third last next previous new old early late
hospital center centre road street lane city town village district state post office
mr mrs ms miss dr prof shri smt sri kumari master baby late col capt sh
continue continued start started stop stopped give given advise advised review monitor monitored plan planned follow followup
kindly attend attendant attendants attending bring brought called contact family advice discharge admit admitted refer referral
report reports reported note noted examination findings history present presented presenting complaint complaints currently
recommended recommend repeat avoid maintain maintained ensure ensured check checked continue: today tomorrow immediately urgent
normal abnormal improved improving stable unstable sent send forwarded forward received receive
""")
HI_STOP = frozenset("""
का की के को में से ने पर है हैं था थी थे और या यह वह इस उस एक भी तो ही नहीं नही कि जो कौन क्या कब कैसे क्यों यहाँ वहाँ
नाम पता मोबाइल फोन फ़ोन लिंग आयु उम्र वर्ष साल दिन तारीख तिथि भर्ती छुट्टी निदान दवाइयाँ दवाई दवा जाँच जांच रोगी मरीज मरीज़
पुरुष महिला स्त्री पिता पति पत्नी माता पुत्र पुत्री बेटे बेटी सुपुत्र सुपुत्री श्री श्रीमती श्रीमान कुमारी डॉ डॉक्टर
बुखार खांसी खाँसी दर्द पेट सिर सीने कमजोरी उल्टी दस्त शिकायत टैब कैप इंजेक्शन सिरप गोली सुबह शाम रात दोपहर
के पास सामने पीछे बगल पर ने बताया बताई कहा कहा है गाँव मोहल्ला शहर जिला राज्य पिन कोड
मधुमेह डेंगू मलेरिया टायफाइड निमोनिया दमा एनीमिया पीलिया हृदयाघात क्षय रोग संक्रमण
ओपीडी पर्ची दिनांक संख्या पंजीकरण क्रम तीव्र उच्च रक्तचाप मूत्र काटना काटने संक्रमण गुर्दा हड्डी पथरी फ्रैक्चर क्षति हृदय जांघ पैर
""".split())

NAME_LABEL_STOP = _words("""
age sex male female address phone mobile contact dob date uhid mrn reg id email admitted admission discharge
discharged diagnosis dx treatment vitals investigations advice alt abha policy insurance guardian resident
residing living from with and of the at on in for who whose was is has had aged years yrs year old
""")

# header vocabulary: output headers made only of these words are kept, everything else is renamed
HEADER_WORDS = _words("""
mrn uhid reg no number id patient name pt full first last middle surname age years sex gender m f dob birth date
phone mobile contact telephone tel email mail address addr residence city town state pin pincode zip code ward
admission admitted admit discharge discharged disch dt doa dod diagnosis dx final principal diagnosis diagnoses
medicines medicine medication medications drug drugs treatment rx remarks remark comments comment notes note
procedure los stay days day length guardian father husband relative kin attendant hospital department dept labs
lab vitals abha insurance policy uid sr sl serial s on of by the and or hb wbc bp hr temp spo2 weight height
naam umar ghar ka pata dawai bimari tareekh sex linga ling aayu nirnay ke ki
""") | frozenset("""
पंजीकरण संख्या रोगी मरीज का नाम आयु उम्र लिंग फोन फ़ोन मोबाइल पता भर्ती छुट्टी तिथि निदान रोग पिता पति
जन्म दवा दवाई क्रम तारीख पिन शहर
""".split())


@lru_cache(maxsize=None)
def _load(name: str) -> frozenset[str]:
    out = set()
    for line in (_DATA / name).read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            out.add(line)
    return frozenset(out)


def first_names() -> frozenset[str]:
    return _load("first_names.txt")


def surnames() -> frozenset[str]:
    return _load("surnames.txt")


def cities() -> frozenset[str]:
    return _load("cities.txt")


@lru_cache(maxsize=None)
def name_skeletons() -> frozenset[str]:
    """Phonetic keys of all gazetteer names with >= 3 key chars (for Devanagari / spelling variants)."""
    keys = set()
    for n in first_names() | surnames():
        k = skeleton(n)
        if len(k) >= 3:
            keys.add(k)
    return frozenset(keys)


@lru_cache(maxsize=None)
def _veto_skeletons() -> frozenset[str]:
    return frozenset(skeleton(w) for w in (DRUG_WORDS | CLINICAL_WORDS) if len(w) >= 4)


def is_drug(tok: str) -> bool:
    return tok.lower().rstrip(".") in DRUG_WORDS


def is_clinical(tok: str) -> bool:
    return tok.lower().rstrip(".") in CLINICAL_WORDS


def is_common(tok: str) -> bool:
    t = tok.lower().rstrip(".")
    return t in COMMON_WORDS or tok in HI_STOP


def is_gaz_first(tok: str) -> bool:
    return tok.lower().rstrip(".") in first_names()


def is_gaz_last(tok: str) -> bool:
    return tok.lower().rstrip(".") in surnames()


def is_gaz_name(tok: str) -> bool:
    t = tok.lower().rstrip(".")
    return t in first_names() or t in surnames()


def deva_gaz_name(tok: str) -> bool:
    """Devanagari token whose phonetic key equals a gazetteer name's key."""
    k = skeleton(tok)
    return len(k) >= 3 and k in name_skeletons() and k not in _veto_skeletons()
