from fc.ProcessSchedules import ProcessSchedules
from fc.ProcessScheduleStatus import ProcessScheduleStatus
from fc.DeployedPackage import DeployedPackage
from fc.EnvironmentAtomAttachment import EnvironmentAtomAttachment
from fc.Environment import Environment
import os
import sys
import argparse
from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
import json
from core.Setup import Setup
from enum import Enum



Setup(["../../setting_private.env", "setting.env"])


class AddedItemType(Enum):
    No = 1
    ENABLED = 2
    DISABLED = 4

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


def parse_args() -> tuple[str, list[str] | None]:
    """Parse command line arguments.

    The first (positional) argument is the environment type - one of ALL,
    TEST or PROD - and selects the value of Environment.EnvironmentType
    used to fetch environments.

    Additionally, any number of --env-prefix (-e) parameters can be passed.
    Only environments whose name starts with one of the given prefixes
    will be processed. When no --env-prefix is given, all environments
    (of the selected type) are processed (original behaviour).
    """
    parser = argparse.ArgumentParser(description="Process Boomi process schedules")
    parser.add_argument(
        "env_type",
        nargs="?",
        choices=["ALL", "TEST", "PROD"],
        default="PROD",
        help=(
            "Environment type to fetch - ALL, TEST or PROD "
            "(Environment.EnvironmentType). Defaults to PROD when omitted."
        ),
    )
    parser.add_argument(
        "-e", "--env-prefix",
        action="append",
        default=None,
        dest="env_prefixes",
        metavar="PREFIX",
        help=(
            "Prefix of the environment name to process. Can be specified "
            "multiple times (e.g. -e PROD- -e UAT-) to process several "
            "environments. When omitted, all environments are processed."
        ),
    )
    args = parser.parse_args()
    return args.env_type, args.env_prefixes


def env_matches(env_name: str, env_prefixes: list[str] | None) -> bool:
    """Return True if the environment should be processed."""
    if not env_prefixes:
        return True
    return any(env_name.startswith(prefix) for prefix in env_prefixes)


if __name__ == '__main__':

    env_type, env_prefixes = parse_args()

    account_id, username, password = validate_environment()

    # setup access to the BoomiAPI
    env = BoomiAPI(account_id, username, password)

    # 1. get environments
    environment_type = getattr(Environment.EnvironmentType, env_type)
    environments = Environment(env, environment_type)
    environments.execute()

    itms = []
    count_total=0
    for runtime_env in environments.result:

        # skip environments that do not match any of the requested prefixes
        if not env_matches(runtime_env["name"], env_prefixes):
            continue
        print(runtime_env["name"], end="", flush=True)

        # 2. get attached Environment vs atomID
        atom = EnvironmentAtomAttachment(env, runtime_env["id"])
        atom.execute()

        env_detail = []

        # 3. list all deploy packages
        packages = DeployedPackage(env, runtime_env["id"])
        packages.execute()

        count=0

        # 4. scheduled processes
        for package in packages.result:
            added_item = False
            enabled = True

            # 4.1 scheduled processes
            schedules = ProcessSchedules(env, package["componentId"], atom.result[0]["atomId"])
            schedules.execute()

            has_schedule = any(len(schedule_itm["Schedule"]) > 0 for schedule_itm in schedules.result)
            if has_schedule:
                added_item = True

                # 4.2 get enable/disable state
                status = ProcessScheduleStatus(env, package["componentId"], atom.result[0]["atomId"])
                status.execute()
                enabled = True if len(status.result)==0 else status.result[0]["enabled"]

                for schedule_itm in schedules.result:
                    schedule_itm["enabled"] = enabled
                env_detail.extend(schedules.result)
                count += 1

            print(("+" if enabled else "-") if added_item else ".", end="", flush=True)

        print(f": {count}", end="", flush=True)
        print()
        count_total+=count
        itms.append({
            "envName": runtime_env["name"],
            "envClassification": runtime_env["classification"],
            "detail": env_detail,
        })

    output = {"itms": itms}
    print(f"Total scheduled processes: {count_total}")

    output_text = json.dumps(output, ensure_ascii=False)
    print(output_text)
    BoomiBase.dump_content(output_text, "output/process_schedules %date%.json")
