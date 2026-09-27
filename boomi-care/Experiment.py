import os
import sys
from core.BoomiAPI import BoomiAPI
from fc.ExecutionSummaryRecord import ExecutionSummaryRecord
from core.Setup import Setup


Setup(["../../setting_private.env", "setting.env"])

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

if __name__ == '__main__':

    account_id, username, password = validate_environment()

    # setup access to the BoomiAPI
    env = BoomiAPI(account_id, username, password)

    audit = ExecutionSummaryRecord(env,
                            go_back=5)
    audit.execute()
    print(audit)
    audit.dump("output/execution_summary_sumrecord %date%.csv")

