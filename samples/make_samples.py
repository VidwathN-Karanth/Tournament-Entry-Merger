"""Generate stand-in sample exports so the pipeline can be exercised end-to-end.

Replace these with the real ChessFee / ChessWorld / CircleChess exports when
they are available -- the column headers here follow plan section 3 exactly.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent

CHESSFEE = pd.DataFrame(
    [
        # NAME, FIDE_ID, aicfno, tnscano, DOB, GENDER, MOBILE_NUMBER, Email, DISTRICT, STATE, AGE_CATEGORY, amount
        ["Ravi Kumar", "25601234", "AICF1001", "KSCA501", "12-05-2010", "M", "9876543210", "ravi@example.com", "Bengaluru Urban", "Karnataka", "U14", "500"],
        ["Ananya Rao", "-", "AICF1002", "KSCA502", "03-11-2012", "F", "9876500011", "ananya@example.com", "Mysuru", "Karnataka", "U12", "500"],
        ["Zoya Khan", "0", "AICF ID not available", "-", "22-07-2011", "F", "9876500012", "zoya@example.com", "Hubballi", "Karnataka", "U14", "500"],
        ["Arjun Nair", "25609999", "AICF1004", "KSCA504", "01-01-2009", "M", "9876500013", "arjun@example.com", "Bengaluru Rural", "Karnataka", "U16", "600"],
        ["Bhavya S", "N/A", "AICF1005", "00", "09-09-2013", "F", "9876500014", "bhavya@example.com", "Tumakuru", "Karnataka", "U12", "500"],
    ],
    columns=["NAME", "FIDE_ID", "aicfno", "tnscano", "DOB", "GENDER", "MOBILE_NUMBER", "Email", "DISTRICT", "STATE", "AGE_CATEGORY", "amount"],
)

CHESSWORLD = pd.DataFrame(
    [
        # Name, FIDE ID, AICF ID, KSCA ID, DOB, Gender, Phone, Email, District, State, Category, Amount Paid, Date
        ["Ravi Kumar", "25601234", "AICF1001", "KSCA501", "12-05-2010", "M", "9876543210", "ravi@example.com", "Bengaluru Urban", "Karnataka", "U14", "500", "05-08-2026 10:15"],
        ["Meera Iyer", "25607777", "AICF1010", "KSCA510", "18-02-2011", "F", "9876500020", "meera@example.com", "Mangaluru", "Karnataka", "U14", "500", "03-08-2026 09:00"],
        ["Arjun Nair", "UNRATED", "AICF1004", "KSCA504", "01-01-2009", "M", "9876500013", "arjun@example.com", "Bengaluru Rural", "Karnataka", "U16", "600", "07-08-2026 18:40"],
        ["Karan Shetty", "25608888", "", "KSCA511", "27-03-2008", "M", "9876500021", "karan@example.com", "Udupi", "Karnataka", "U18", "600", "01-08-2026 12:00"],
        ["Nisha Gowda", "", "", "", "14-06-2014", "F", "9876500022", "nisha@example.com", "Hassan", "Karnataka", "U10", "450", "not a date"],
    ],
    columns=["Name", "FIDE ID", "AICF ID", "KSCA ID", "DOB", "Gender", "Phone", "Email", "District", "State", "Category", "Amount Paid", "Date"],
)

CIRCLECHESS = pd.DataFrame(
    [
        # name, fide_id, aicf_id, state_id, dob, gender, mobile_number, email, district, state, category, amount
        ["Meera Iyer", "25607777", "AICF1010", "KSCA510", "18-02-2011", "F", "9876500020", "meera@example.com", "Mangaluru", "Karnataka", "U14", "500"],
        ["Aditya Bhat", "25605555", "AICF1020", "KSCA520", "30-10-2010", "M", "9876500030", "aditya@example.com", "Shivamogga", "Karnataka", "U14", "500"],
        ["Ananya Rao", "", "AICF1002", "KSCA502", "03-11-2012", "F", "9876500011", "ananya@example.com", "Mysuru", "Karnataka", "U12", "500"],
        ["Chirag Patil", "0", "0", "0", "05-05-2015", "M", "9876500031", "chirag@example.com", "Belagavi", "Karnataka", "U10", "450"],
        ["Deepa Menon", "", "AICF1021", "", "11-11-2011", "F", "9876500032", "deepa@example.com", "Kalaburagi", "Karnataka", "U14", "500"],
    ],
    columns=["name", "fide_id", "aicf_id", "state_id", "dob", "gender", "mobile_number", "email", "district", "state", "category", "amount"],
)

NATIONAL_RATING_LIST = pd.DataFrame(
    [["25605555", "Aditya Bhat", "1420"]], columns=["fide_id", "name", "rating"]
)


def main() -> None:
    CHESSFEE.to_csv(HERE / "ChessFee.csv", index=False)
    CHESSWORLD.to_csv(HERE / "ChessWorld.csv", index=False)
    with pd.ExcelWriter(HERE / "CircleChess.xlsx", engine="openpyxl") as writer:
        CIRCLECHESS.to_excel(writer, sheet_name="Participants", index=False)
        NATIONAL_RATING_LIST.to_excel(writer, sheet_name="NationalRatingList", index=False)
    print(f"Wrote sample files to {HERE}")


if __name__ == "__main__":
    main()
