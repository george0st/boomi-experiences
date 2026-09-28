from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from enum import Enum


class ExecutionSummaryRecord(BoomiBase):
    class AuditType(Enum):
        ALL = 1
        LOGIN = 2

    def __init__(self, env_boomi: BoomiAPI, go_back=-1, go_back_month=2, date_from = None, date_to = None, threads = 5, step_minutes = 30, atomId = ""):
        super().__init__(env_boomi, go_back, go_back_month, date_from, date_to, threads, step_minutes)
        self.atomId=atomId

    def _build_query(self, atomId, date_from, date_to):
        return "{\"QueryFilter\":{\"expression\":" \
               "{\"operator\": \"and\",\"nestedExpression\":[" \
               "{\"argument\": [\"" + atomId + "\"],\"operator\": \"EQUALS\",\"property\": \"atomId\"}," \
               "{\"argument\": [\"" + date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + date_to.strftime("%Y-%m-%dT%H:%M:%SZ") + "\"],\"operator\": \"BETWEEN\",\"property\": \"timeBlock\"}" \
               "]}}}"

    def _run_interval(self, atomId, interval):
        date_from, date_to = interval
        query = self._build_query(atomId, date_from, date_to)
        return self.env_boomi.query("ExecutionSummaryRecord", query)

    def execute(self):
        partial_results = self.run_parallel(self.atomId, self._run_interval)
        self.result = self.merge_list_results(partial_results)


    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

