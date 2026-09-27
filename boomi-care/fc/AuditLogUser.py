from dateutil.relativedelta import relativedelta
from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from datetime import datetime, timedelta



class AuditLogUser(BoomiBase):

    def __init__(self, env_boomi: BoomiAPI, email, all_logins=True, go_back=-1, go_back_month=2):
        super().__init__(env_boomi)
        self.email = email
        self.all_logins = all_logins
        date_now = datetime.now()
        if go_back != -1:
            self.date_from = (date_now - timedelta(days=go_back)).replace(hour=0, minute=0, second=0, microsecond=0) #"2026-04-15T00:59:59Z"
        else:
            self.date_from = (date_now - relativedelta(months=go_back_month)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0)
        self.date_to = date_now  # 2026-04-15T23:59:59Z"
        self.logins = {}

    def execute(self):

        eml = "" if self.email is None else "{\"argument\": [\"" + self.email + "\"],\"operator\": \"EQUALS\",\"property\": \"userId\"},"
        query = "{\"QueryFilter\":{\"expression\":" \
                "{\"operator\": \"and\",\"nestedExpression\":[" \
                "{\"argument\": [\"user\"],\"operator\": \"EQUALS\",\"property\": \"type\"}," \
                "{\"argument\": [\"" + self.date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + self.date_to.strftime("%Y-%m-%dT%H:%M:%SZ") +"\"],\"operator\": \"BETWEEN\",\"property\": \"date\"}" \
                "]}}}"

        result = self.env_boomi.query("AuditLog",query)
        self.result = result

    def __str__(self):
        output = ""
        for itm in self.result:
            output += f"{itm}\n"
        return output

