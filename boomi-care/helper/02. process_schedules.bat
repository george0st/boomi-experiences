rem -- RUN environments, deploy packages, component metadata

cd ..
python ProcessSchedules.py PROD -e "03-AZURE_PROD"
python ComponentMetadata.py

cd genmd
rem -- GENERATE markdown files
rundate.py ./schedules/generate_schedule_heatmap.py --json "../output/process_schedules <date>.json" --csv "../output/component_metadata <date>.csv" --out "../output/schedule-heatmap <date>.html"

rem -- CLEAN files older than 2 days
fileclean.py "../output/" process_schedules* 2
fileclean.py "../output/" component_metadata* 2
fileclean.py "../output/" schedule-heatmap* 2



