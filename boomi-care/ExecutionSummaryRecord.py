from datetime import datetime, timedelta, date
import os
import sys
import time
from contextlib import contextmanager
from core.BoomiAPI import BoomiAPI
from fc.ExecutionSummaryRecord import ExecutionSummaryRecord
from core.Setup import Setup


Setup(["../../setting_private.env", "setting.env"])

@contextmanager
def timer(nazev="code"):
    start = time.perf_counter()
    try:
        yield
    finally:
        total = time.perf_counter() - start
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        s = total % 60
        print(f"{nazev} – Time processing: {h} h {m} min {s:.3f} s "
              f"(TOTAL: {total:.3f} s)\n")

def validate_environment() -> tuple[str, str, str]:
    """Validate required environment variables and return credentials"""
    account_id = os.getenv("BOOMI_ACCOUNT")
    username = os.getenv("BOOMI_USER")
    password = os.getenv("BOOMI_SECRET")

    if not all([account_id, username, password]):
        print("❌ Error: Missing required environment variables")
        print("   Please set: BOOMI_ACCOUNT, BOOMI_USER, BOOMI_SECRET")
        print("   You can also create a .env file with these variables")
        sys.exit(1)

    return account_id, username, password

def process_day(env, current, atomId, threads = 8, step_minutes = 10):

    print(f"Processing {current.strftime("%Y.%m.%d")} ...")
    with timer("Execution"):
        # setup access to the BoomiAPI

        date_from = datetime(current.year,current.month, current.day, 0,0,0)
        date_to = datetime(current.year,current.month, current.day, 23,59,59)

        audit = ExecutionSummaryRecord(env,
                                date_from = date_from,
                                date_to = date_to,
                                go_back = 0,
                                #group_items = ['atomName', 'atomId', 'nodeId', 'processName', 'processId', 'status', 'executionType'],
                                #gount_items = ['inboundDocumentCount', 'inboundErrorDocumentCount', 'outboundDocumentCount'],
                                threads = threads,
                                step_minutes = step_minutes,
                                atomId=atomId)
        audit.execute()
        print(audit)
        audit.dump(f"output/execution_sum_record %date% ({date_from.strftime("%Y%m%d")}).csv")



if __name__ == '__main__':

    account_id, username, password = validate_environment()

    date_from = date(2026,8, 6)
    date_to = date(2026,8, 7)

    # add maximal amount of cycles
    current = date_from
    try:
        while current <= date_to:
            env = BoomiAPI(account_id, username, password)
            process_day(env, current, "<atomId>", 8, 10)
            current += timedelta(days=1)
    except Exception as e:
        print(f"EXCEPTION: {e}")
    
