from app.ingest.backfill_judgment_metadata import extract_bench_strength, extract_date

SAMPLE_SINGLE_JUDGE = """Masud Khan v State Of Uttar Pradesh
Supreme Court of India

26 September 1973
Writ Petition No. 117 of 1973
The Judgment was delivered by : A. Alagiriswami, J.
1.  Petitioner Masud Khan prays for his release"""

SAMPLE_MULTI_JUDGE = """Some Case v Another Party
Supreme Court of India

3 May 2007
Appeal (Crl.) 244 of 2006
The Judgment was delivered by: G. P. Mathur, J. and R. V. Raveendran, J.
1. This appeal, by special leave"""

SAMPLE_NO_DATE = """A Case With No Extractable Header
1. This document has no recognizable date or judge line at all."""


def test_extract_date_single_digit_day():
    assert extract_date(SAMPLE_SINGLE_JUDGE) == "1973-09-26"


def test_extract_date_returns_none_when_absent():
    assert extract_date(SAMPLE_NO_DATE) is None


def test_extract_bench_strength_single_judge():
    assert extract_bench_strength(SAMPLE_SINGLE_JUDGE) == 1


def test_extract_bench_strength_multi_judge():
    assert extract_bench_strength(SAMPLE_MULTI_JUDGE) == 2


def test_extract_bench_strength_returns_none_when_absent():
    assert extract_bench_strength(SAMPLE_NO_DATE) is None
