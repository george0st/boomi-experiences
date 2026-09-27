rem -- RUN environments, deploy packages, component metadata

cd ..
python Environment.py
python DeployedPackage.py
python ComponentMetadata.py


cd genmd
rem -- GENERATE markdown files
rundate.py ./deployment/env_deploy.py "../output/environment <date>.csv" "../output/deployed_package <date>.csv" "../output/component_metadata <date>.csv" "../output/env_deploy <date>.md"


rem -- CLEAN files older than 2 days
fileclean.py "../output/" environment* 2
fileclean.py "../output/" deployed_package* 2
fileclean.py "../output/" component_metadata* 2
fileclean.py "../output/" env_deploy* 2



