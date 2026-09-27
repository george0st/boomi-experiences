import requests
from requests.auth import HTTPBasicAuth


class BoomiAPI:

    class Counters:
        def __init__(self):
            pass

    HTTP_HEADER = {"Content-Type": "application/json", "Accept": "application/json"}

    def __init__(self, accountId, user_name, pwd, url="https://api.boomi.com/api/rest/v1/"):
        self._accountId = accountId
        self._user_name=user_name
        self._pwd=pwd
        self._url=url

    # Call with paging
    def query_group(self, action, str_query="{\"QueryFilter\":{}}", group_items = None, count_items = None):
        return_data={}

        url=f"{self._url}{self._accountId}/{action}/query"
        response = requests.post(url,
                                 data = str_query,
                                 auth = HTTPBasicAuth(self._user_name, self._pwd),
                                 headers = BoomiAPI.HTTP_HEADER)
        response_data = response.json()

        while True:
            if not response_data.get("result"):
                return {}
#region GROUP DATA
            for response_item in response_data["result"]:
                # create key as the string with separator ',' from all json item names from groups
                key=""
                for itm in group_items:
                    if response_item.get(itm) is not None:
                        key += f"{response_item[itm]},"
                    else:
                        key += ","

                if return_data.get(key) is None:
                    # current key does not exist, create new based on the first item
                    counters = BoomiAPI.Counters()
                    for count_name in count_items:
                        setattr(counters, count_name, response_item[count_name])
                    return_data[key] = counters
                else:
                    counters = return_data[key]
                    # increase values of current dynamic parameters (plus values from response_data for all
                    # items from count_items)
                    for count_name in count_items:
                        counter_value=getattr(counters, count_name, 0)
                        setattr(counters, count_name, counter_value + response_item[count_name])
#endregion

            if response_data.get("queryToken") is not None:
                # get more data
                url = f"{self._url}{self._accountId}/{action}/queryMore"
                response = requests.post(url,
                                         data = response_data["queryToken"],
                                         auth = HTTPBasicAuth(self._user_name, self._pwd),
                                         headers = BoomiAPI.HTTP_HEADER)
                response_data = response.json()
            else:
                return_new_data = []
                for key in return_data.keys():
                    counters = return_data[key]
                    text_counters = ""
                    for count_name in count_items:
                        counter_value = getattr(counters, count_name, 0)
                        text_counters += f"{counter_value},"
                    # TODO: remove last ','
                    return_new_data.append(f"{key}{text_counters}")
                return return_new_data

    # Call with paging
    def query(self, action, str_query="{\"QueryFilter\":{}}"):
        return_data=[]
        url=f"{self._url}{self._accountId}/{action}/query"
        response = requests.post(url,
                                 data = str_query,
                                 auth = HTTPBasicAuth(self._user_name, self._pwd),
                                 headers = BoomiAPI.HTTP_HEADER)
        response_data = response.json()

        while True:
            if not response_data.get("result"):
                return {}
            return_data += response_data["result"]
            if response_data.get("queryToken") is not None:
                # get more data
                url = f"{self._url}{self._accountId}/{action}/queryMore"
                response = requests.post(url,
                                         data = response_data["queryToken"],
                                         auth = HTTPBasicAuth(self._user_name, self._pwd),
                                         headers = BoomiAPI.HTTP_HEADER)
                response_data = response.json()
            else:
                return return_data


    # Simple call without paging
    def call(self, action, parameter):
        url=f"{self._url}{self._accountId}/{action}/{parameter}"
        response = requests.get(url,
                                auth = HTTPBasicAuth(self._user_name, self._pwd),
                                headers = BoomiAPI.HTTP_HEADER)
        return response.json()
