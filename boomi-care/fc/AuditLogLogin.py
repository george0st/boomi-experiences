from xmlrpc.client import DateTime
from dateutil.relativedelta import relativedelta
from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase
from datetime import datetime, timedelta
from enum import Enum


class AuditLogLogin(BoomiBase):
    class AuditType(Enum):
        ALL = 1
        LOGIN = 2

    def __init__(self, env_boomi: BoomiAPI, email, all_logins=True, go_back=-1, go_back_month=2, audit_type=AuditType.LOGIN):
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
        self.audit_type = audit_type

    def execute(self):

        eml = "" if self.email is None else "{\"argument\": [\"" + self.email + "\"],\"operator\": \"EQUALS\",\"property\": \"userId\"},"
        if self.audit_type == AuditLogLogin.AuditType.LOGIN:
            self.logins = {}

            query = "{\"QueryFilter\":{\"expression\":" \
                    "{\"operator\": \"and\",\"nestedExpression\":[" \
                    "{\"argument\": [\"account\"],\"operator\": \"EQUALS\",\"property\": \"type\"}," \
                    "{\"argument\": [\"SUCCESS\"],\"operator\": \"EQUALS\",\"property\": \"modifier\"}," \
                    "{\"argument\": [\"ON_ENTRY\"],\"operator\": \"EQUALS\",\"property\": \"action\"}," + eml + \
                    "{\"argument\": [\"" + self.date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + self.date_to.strftime("%Y-%m-%dT%H:%M:%SZ") +"\"],\"operator\": \"BETWEEN\",\"property\": \"date\"}" \
                    "]}}}"

            result = self.env_boomi.query("AuditLog",query)

            for itm in result:
                if self.logins.get(itm["userId"]) == None:
                    self.logins[itm['userId']]=[DateTime(itm['date'])]
                else:
                    self.logins[itm['userId']].append(DateTime(itm['date']))
    #            self.logins.append(DateTime(itm['date']))
            for key in self.logins.keys():
                self.logins[key] = sorted(self.logins[key], reverse=True)
        else:

            # query = "{\"QueryFilter\":{\"expression\":" \
            #         "{\"operator\": \"and\",\"nestedExpression\":[" \
            #         "{\"argument\": [\"account\"],\"operator\": \"EQUALS\",\"property\": \"type\"}," + eml + \
            #         "{\"argument\": [\"" + self.date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + self.date_to.strftime("%Y-%m-%dT%H:%M:%SZ") +"\"],\"operator\": \"BETWEEN\",\"property\": \"date\"}" \
            #        "]}}}"
            query = "{\"QueryFilter\":{\"expression\":" \
                    "{\"operator\": \"and\",\"nestedExpression\":[" + eml + \
                    "{\"argument\": [\"" + self.date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + self.date_to.strftime("%Y-%m-%dT%H:%M:%SZ") +"\"],\"operator\": \"BETWEEN\",\"property\": \"date\"}" \
                   "]}}}"

            result = self.env_boomi.query("AuditLog",query)
            self.result = result


    def __str__(self):
        if self.audit_type == AuditLogLogin.AuditType.LOGIN:
            output = "userId,lastlogin"
            if self.all_logins:
                output+=",logins"

            for key in self.logins.keys():
                if len(output)>0:
                    output += "\n"

                output += f"{key},{str(self.logins[key][0])}"
                if self.all_logins:
                    logins = ""
                    for itm in self.logins[key]:
                        if len(logins) > 0:
                            logins += ", "
                        logins += str(itm)
                    output += f",\"{logins}\""
        else:
            output = ""
            for itm in self.result:
                output += f"{itm}\n"
        return output

