from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase


class ProcessSchedules(BoomiBase):

    def __init__(self, env_boomi: BoomiAPI, componentId, atomId):
        super().__init__(env_boomi)
        self.componentId = componentId
        self.atomId = atomId

    def execute(self):

        query = "{\"QueryFilter\":{\"expression\":" \
               "{\"operator\": \"and\",\"nestedExpression\":[" \
               "{\"argument\": [\"" + self.componentId + "\"],\"operator\": \"EQUALS\",\"property\": \"processId\"}," \
               "{\"argument\": [\"" + self.atomId + "\"],\"operator\": \"EQUALS\",\"property\": \"atomId\"}" \
                "]}}}"
        result = self.env_boomi.query("ProcessSchedules",query)
        self.result = result

    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

