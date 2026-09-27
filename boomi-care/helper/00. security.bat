rem -- RUN user roles, audit log login

cd ..
python UserRole.py
python AuditlogLogin.py


cd genmd
rem -- GENERATE markdown files
rundate.py ./security/user_roles_csv_to_md.py "../output/users_roles <date>.txt" "../output/users_roles <date>.md"
rundate.py ./security/group_by_role.py -i "../output/users_roles <date>.txt" -o "../output/users_roles_groupby_role <date>" -f md -t generated
rundate.py ./security/auditlog_to_md.py "../output/audit_log <date>.csv" "../output/audit_log <date>.md" --format png


rem -- CLEAN files older than 2 days
fileclean.py "../output/" users_roles* 2
fileclean.py "../output/" audit_log* 2
