from core.BoomiAPI import BoomiAPI
from core.BoomiBase import BoomiBase


class UsersRoles(BoomiBase):
    class User:

        def __init__(self, firstName, lastName, userId, role):
            self.firstName = firstName
            self.lastName = lastName
            self.userId = userId
            self.roles = [role]

    def __init__(self, env_boomi: BoomiAPI):
        super().__init__(env_boomi)
        self.users ={}

    def execute(self):

        # get list of roles
        roles={}
        result = self.env_boomi.query("Role")
        for itm in result:
            roles[itm['id']]=itm['name']

        # get list of users (and map the roles)
        self.users = {}
        result = self.env_boomi.query("AccountUserRole")
        for itm in result:
            if self.users.get(itm["userId"]) == None:
                self.users[itm["userId"]]=UsersRoles.User(
                    itm["firstName"],
                    itm["lastName"],
                    itm["userId"],
                    roles[itm["roleId"]])
            else:
                self.users[itm["userId"]].roles.append(roles[itm["roleId"]])

    def __str__(self):

        output="userId,firstName,lastName,roles"
        for user in self.users.values():
            roles=""
            for role in user.roles:
                roles += role if len(roles)==0 else "," + role
            if len(output)>0:
                output += "\n"
            output += f"{user.userId},{user.firstName},{user.lastName},\"{roles}\""
        return output

