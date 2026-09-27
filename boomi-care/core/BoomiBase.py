from core.BoomiAPI import BoomiAPI
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from concurrent.futures import ThreadPoolExecutor


class BoomiBase:

    def __init__(self, env_boomi: BoomiAPI, go_back=-1, go_back_month=2, date_from = None, date_to = None, threads = 5, step_minutes=30):
        self.env_boomi = env_boomi
        self.threads = threads
        self.step_minutes = step_minutes

        if (date_from is not None) or (date_to is not None):
            self.date_from = date_from
            self.date_to = date_to
        else:
            date_now = datetime.now()
            if go_back != -1:
                self.date_from = (date_now - timedelta(days=go_back)).replace(hour=0, minute=0, second=0, microsecond=0) #"2026-04-15T00:59:59Z"
            else:
                self.date_from = (date_now - relativedelta(months=go_back_month)).replace(
                    day=1, hour=0, minute=0, second=0, microsecond=0)
            self.date_to = date_now  # 2026-04-15T23:59:59Z"

    def split_intervals(self):
        # Split the time range <self.date_from, self.date_to> into chunks of step_minutes minutes.
        # The chunks do not overlap: because the BETWEEN filter is inclusive on both ends, every
        # chunk (except the last) ends one second before the next chunk starts.
        intervals = []
        step = timedelta(minutes=self.step_minutes)
        start = self.date_from
        while start < self.date_to:
            next_start = min(start + step, self.date_to)
            end = next_start if next_start >= self.date_to else next_start - timedelta(seconds=1)
            intervals.append((start, end))
            start = next_start
        return intervals

    def run_parallel(self, run_func):
        # Split the time range into chunks and run run_func((date_from, date_to)) in parallel
        # across self.threads threads. Returns the list of partial results in chunk order.
        intervals = self.split_intervals()
        with ThreadPoolExecutor(max_workers=self.threads) as executor:
            return list(executor.map(run_func, intervals))

    @staticmethod
    def merge_list_results(partial_results):
        # Merge partial results (lists of items) from the query method into a single list.
        merged = []
        for result in partial_results:
            if result:
                merged += result
        return merged

    @staticmethod
    def merge_grouped_results(partial_results, group_items, count_items):
        # Merge partial results from the query_group method. query_group returns a list of
        # strings in the form "<group_items...>,<count_items...>,". The same key can appear
        # in multiple chunks, so the counts must be summed.
        group_count = len(group_items)
        count_count = len(count_items)
        merged = {}
        order = []

        for result in partial_results:
            if not result:
                continue
            for row in result:
                parts = row.split(",")
                key = ",".join(parts[:group_count]) + ","
                counts = parts[group_count:group_count + count_count]

                if key not in merged:
                    merged[key] = [int(c) if c else 0 for c in counts]
                    order.append(key)
                else:
                    for i, c in enumerate(counts):
                        merged[key][i] += int(c) if c else 0

        return [key + "".join(f"{c}," for c in merged[key]) for key in order]

    def dump(self, file="output/users_roles %date%.txt", encoding="utf-8"):

        # replace %date%
        current_date = datetime.now().strftime("%Y-%m-%d")
        file=file.replace("%date%",current_date)

        # replace %datetime%
        current_datetime = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        file=file.replace("%datetime%",current_date)

        with open(file, "w", encoding=encoding) as f:
            f.write(self.__str__())

    @staticmethod
    def dump_content(content: str, file="output/users_roles %date%.txt", encoding="utf-8"):

        # replace %date%
        current_date = datetime.now().strftime("%Y-%m-%d")
        file=file.replace("%date%",current_date)

        # replace %datetime%
        current_datetime = datetime.now().strftime("%Y-%m-%d %H-%M-%S")
        file=file.replace("%datetime%",current_date)

        with open(file, "w", encoding=encoding) as f:
            f.write(content)