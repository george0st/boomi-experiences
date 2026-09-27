from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase


class ExecutionRecord(BoomiBase):

    def __init__(self, env_boomi: BoomiAPI, go_back=-1, go_back_month=2, date_from = None, date_to = None, group_items = None, count_items = None, threads = 5, step_minutes = 10):
        super().__init__(env_boomi, go_back, go_back_month, date_from, date_to, threads, step_minutes)

        self.result = []
        self.group_items = group_items
        self.count_items = count_items

    def _build_query(self, date_from, date_to):
        return "{\"QueryFilter\":{\"expression\":" \
               "{\"operator\": \"and\",\"nestedExpression\":[" \
               "{\"argument\": [\"" + date_from.strftime("%Y-%m-%dT%H:%M:%SZ") + "\", \"" + date_to.strftime("%Y-%m-%dT%H:%M:%SZ") + "\"],\"operator\": \"BETWEEN\",\"property\": \"executionTime\"}" \
               "]}}}"

    def _run_interval(self, interval):
        date_from, date_to = interval
        query = self._build_query(date_from, date_to)
        return self.env_boomi.query_group("ExecutionRecord",
                                          query,
                                          self.group_items,
                                          self.count_items)

    def execute(self):
        partial_results = self.run_parallel(self._run_interval)
        self.result = self.merge_grouped_results(partial_results, self.group_items, self.count_items)

    def _get_index(self, items, name):
        for index in range(len(items)):
            if (items[index] == name):
                return index
        return -1

    def __str__(self):
        output = "date,date_from,date_to,"
        for itm in self.group_items:
            output += f"{itm},"
        for itm in self.count_items:
            output += f"{itm},"
        output += "totalDocumentCount,countryName\n"

        processNameIndex=self._get_index(self.group_items, "processName")
        inboundErrorDocumentCountIndex=self._get_index(self.count_items, "inboundErrorDocumentCount")
        inboundDocumentCountIndex=self._get_index(self.count_items, "inboundDocumentCount")
        outboundDocumentCountIndex=self._get_index(self.count_items, "outboundDocumentCount")


        for itm in self.result:
            items=itm.split(',')

            # Add countryName
            countryName="GLO"
            if processNameIndex>-1:
                if len(items[processNameIndex])>0:
                    originalName=items[processNameIndex].strip()

                    # remove e.g. 'Sub: IT_xxxx' -> 'IT_xxx' -> 'IT'
                    index = originalName.find(':')
                    if index > -1:
                        originalName=originalName[index+1:].strip()

                    # skip beginning with '[' e.g. [MAIN][xxx] xxx ... -> 'GLO'
                    if originalName.startswith('[') == False:
                        index = originalName.find('_')
                        if index > -1:
                            countryName = originalName[0:index].upper()

            # Add totalDocumentCount
            totalDocumentCount=0
            if inboundErrorDocumentCountIndex>-1:
                totalDocumentCount += int(items[len(self.group_items)+inboundErrorDocumentCountIndex])
            if inboundDocumentCountIndex>-1:
                totalDocumentCount += int(items[len(self.group_items) + inboundDocumentCountIndex])
            if outboundDocumentCountIndex>-1:
                totalDocumentCount += int(items[len(self.group_items) + outboundDocumentCountIndex])

            output += f"{self.date_from.strftime("%Y-%m-%d")},{self.date_from},{self.date_to},{itm}{totalDocumentCount},{countryName}\n"

        return output

