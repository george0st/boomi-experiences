from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from enum import Enum


class ComponentMetadata(BoomiBase):
    class AuditType(Enum):
        ALL = 1
        LOGIN = 2

    def __init__(self, env_boomi: BoomiAPI, componentID = None):
        super().__init__(env_boomi)
        self.componentID = componentID

    def execute(self):

        component = "" if self.componentID is None else "{\"argument\": [\"" + self.componentID + "\"],\"operator\": \"EQUALS\",\"property\": \"componentId\"},"
        query = "{\"QueryFilter\":{\"expression\":" \
               "{\"operator\": \"and\",\"nestedExpression\":[" + component + \
               "{\"argument\": [\"true\"],\"operator\": \"EQUALS\",\"property\": \"currentVersion\"}," \
               "{\"argument\": [\"process\"],\"operator\": \"EQUALS\",\"property\": \"type\"}," \
               "{\"argument\": [\"false\"],\"operator\": \"EQUALS\",\"property\": \"deleted\"}" \
               "]}}}"

        result = self.env_boomi.query("ComponentMetadata",query)
        self.result = result


    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

