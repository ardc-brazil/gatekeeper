class ForbiddenException(Exception):
    detail = "forbidden"


class NotAMemberOfTenancyException(ForbiddenException):
    detail = "not_a_member_of_tenancy"
