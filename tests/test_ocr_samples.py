import pytest
from pathlib import Path
from ocr import extract_fields_for_type

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")

def test_gujarat_dl():
    text = load_fixture("gujarat_dl.txt")
    fields = extract_fields_for_type("Driving_License", text)
    
    assert fields["license_number"] == "GJ01 20180012345"
    assert fields["name"] == "PATEL RAMESHBHAI"
    assert fields["dob"] == "14-05-1985"
    assert fields["expiry"] == "13-05-2035"

def test_dl_name_fallback_no_label():
    text = "INDIAN UNION DRIVING LICENCE\nGJ01 20180012345\nPATEL RAMESHBHAI\nS/O: PATEL\nDOB 14-05-1985\nVALID TILL 13-05-2035"
    fields = extract_fields_for_type("Driving_License", text)
    
    assert fields["name"] == "PATEL RAMESHBHAI"

def test_dl_dates_ambiguous_correction():
    # If the OCR mixes them up, Expiry should be the future date, DOB the past/earliest.
    # We will put DOB label near the future date and Expiry label near the past date
    # The sanity pass should correct them.
    text = "DOB: 13-05-2035\nEXPIRY: 14-05-1985"
    fields = extract_fields_for_type("Driving_License", text)
    
    assert fields["dob"] == "14-05-1985"
    assert fields["expiry"] == "13-05-2035"

def test_gujarat_dl_fused_dates():
    text = load_fixture("gujarat_dl_fused.txt")
    fields = extract_fields_for_type("Driving_License", text)
    
    assert fields["license_number"] == "GJ03 20070124952"
    assert fields["name"] == "NARESHBHAI KAPUR"
    assert fields["dob"] == "07-03-1980"
    assert fields["expiry"] == "05-07-2027"

def test_passport_harmeet_singh():
    text = """/ REPUBLIC OF INDIA.
/ Code / Nationality d. ; Passport No.
IND / INDIAN W5469900
/ Surname
SINGH
f Given Name(s)
HARMEET
of Birth / sex
10/11/2002 M
/ Place Of Birth
KURRAIYA KALAN,UTTAR PRADESH
/ Place of Issue
BAREILLY
$T 1 Date of Issue / Date of Expiry
27/01 /2023 26/01 /2033
W5469900<1 IND021 1 107M33012691077395940823<46"""
    fields = extract_fields_for_type("Passport", text)
    assert fields["passport_number"] == "W5469900"
    assert fields["name"] == "Harmeet Singh"
    assert fields["nationality"] in ("IND", "INDIAN")
    assert fields["dob"] == "10-11-2002"
    assert fields["expiry"] == "26-01-2033"
    assert fields["gender"] == "Male"

def test_us_visa_assia_nasreen():
    text = """VISA
Issuing Post Name Control Number
HYDERABAD 20135678o2
Surname
ASSIA NASREEN
Given Narne Visa Type ./Class
FNU R. Bl/B2
Passport Number Birth Date
H8150402 25JAN1965
Entries Issue Date Expiration Date
07DEC2010 03DEC2011 0111.
Annotation
CLEARANCE RECEIVED 04-DEC-2010 C6149107
H8150402<91ND6501255F1112038B3HYD046U0812083"""
    fields = extract_fields_for_type("Visa", text)
    assert fields["visa_number"] in ("C6149107", "H8150402")
    assert fields["name"] == "Assia Nasreen"
    assert fields["visa_type"] in ("B1/B2", "B2")
    assert fields["expiry"] == "03-12-2011"
    assert fields["gender"] == "Female"
    assert fields["entry_validation"] == "Multiple"

def test_passport_gurjinder_singh():
    text = """REPUBLIC OF INDIA
eTtq / Type / Country Code / Passport
p / Surname IND L 9859125
/ Given Name(s)
GURJINDER SINGH
Nationality
INDIAN 04/03/1991
/ Place ot Birth
OTTU DHANI SAROOP SINGH , ARYANA
1 / Place of
CHANDIGARH
Sibate of issue
-J 23/06/2014 22/06/2024"""
    fields = extract_fields_for_type("Passport", text)
    assert fields["passport_number"] == "L9859125"
    assert fields["name"] == "Gurjinder Singh"
    assert fields["nationality"] in ("IND", "INDIAN")
    assert fields["dob"] == "04-03-1991"
    assert fields["expiry"] == "22-06-2024"
    assert fields["gender"] == "Male"

def test_passport_mudassir_kazi():
    text = """VISA
REPUBLIC OF -INDIA
IND / INDIAN B7965523
KAZI
MD MUDASSIR
12/05/1994
NOWDIHA BOKARO, JHARKHAND
DUBAI
22/01 /2024 21/01/2029"""
    fields = extract_fields_for_type("Passport", text)
    assert fields["passport_number"] == "B7965523"
    assert fields["name"] == "Md Mudassir Kazi"
    assert fields["nationality"] in ("IND", "INDIAN")
    assert fields["dob"] == "12-05-1994"
    assert fields["expiry"] == "21-01-2029"
    assert fields["gender"] == "Male"

def test_gujarat_dl_nimesh_kapoor():
    text = """Indian Union Driving Licence
Issued by Government of Gujarat
GJ05 20230034039
Issue Date Validity ( NT ) Validity (TR)
11-10-2023 31-05-2047
Name : NIMESH NARESH KAPOOR
Date or Birth : 01-06-2007 Blood Group : Organ Dono
Son/Daughter/Wite or : NARESH KAPOOR o
Address
49. BHAGYODAY SOC
PALANPUR PATNA
Surat"""
    from ocr.document_type import detect_document_type
    assert detect_document_type(text) == "Driving_License"
    fields = extract_fields_for_type("Driving_License", text)
    assert fields["license_number"] == "GJ05 20230034039"
    assert fields["name"] == "NIMESH NARESH KAPOOR"
    assert fields["dob"] == "01-06-2007"
    assert fields["expiry"] == "31-05-2047"

def test_gujarat_dl_noisy_nimesh():
    text = """Indian UnipmDrpivipyLi.cence'
GJ05 20230034039
Issue Date Validity ( NV) Validity
li-i030i3 31-05-2047
Signatie
Name:: NIMESH NARESH KAPOOR
Date-Of Birth : 01-06-2007
Son/Daughfer/Wife or NARESH- KAPOOR
Address
49, BHAGYODAY SOC
PALANPUR, PATIYA 
Surat"""
    from ocr.document_type import detect_document_type
    assert detect_document_type(text) == "Driving_License"
    fields = extract_fields_for_type("Driving_License", text)
    assert fields["license_number"] == "GJ05 20230034039"
    assert fields["name"] == "NIMESH NARESH KAPOOR"
