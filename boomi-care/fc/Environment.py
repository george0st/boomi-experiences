from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from enum import Enum


class Environment(BoomiBase):
    class EnvironmentType(Enum):
        ALL = 1
        TEST = 2
        PROD = 4

    def __init__(self, env_boomi: BoomiAPI, env_type: EnvironmentType = EnvironmentType.ALL):
        super().__init__(env_boomi)
        self.env_type = env_type

    def execute(self):

        if self.env_type == Environment.EnvironmentType.ALL:
            query = "{}"
        elif self.env_type == Environment.EnvironmentType.TEST:
            query = "{\"QueryFilter\":{\"expression\":" \
                   "{\"operator\": \"and\",\"nestedExpression\":[" \
                   "{\"argument\": [\"TEST\"],\"operator\": \"EQUALS\",\"property\": \"classification\"}" \
                   "]}}}"
        else:
            query = "{\"QueryFilter\":{\"expression\":" \
                   "{\"operator\": \"and\",\"nestedExpression\":[" \
                   "{\"argument\": [\"PROD\"],\"operator\": \"EQUALS\",\"property\": \"classification\"}" \
                   "]}}}"

        result = self.env_boomi.query("Environment",query)
        self.result = result


    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

