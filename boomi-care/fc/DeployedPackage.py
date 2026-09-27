from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from enum import Enum


class DeployedPackage(BoomiBase):
    class AuditType(Enum):
        ALL = 1
        LOGIN = 2

    def __init__(self, env_boomi: BoomiAPI, environmentID = None):
        super().__init__(env_boomi)
        self.environmentID = environmentID

    def execute(self):

        env = "" if self.environmentID is None else "{\"argument\": [\"" + self.environmentID + "\"],\"operator\": \"EQUALS\",\"property\": \"environmentId\"},"

        query = "{\"QueryFilter\":{\"expression\":" \
               "{\"operator\": \"and\",\"nestedExpression\":[" + env + \
               "{\"argument\": [\"true\"],\"operator\": \"EQUALS\",\"property\": \"active\"}," \
                 "{\"operator\": \"or\",\"nestedExpression\":[" \
                 "{\"argument\": [\"process\"],\"operator\": \"EQUALS\",\"property\": \"componentType\"}" \
                 "]}" \
               "]}}}"

        result = self.env_boomi.query("DeployedPackage",query)
        self.result = result


    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

