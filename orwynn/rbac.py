from typing import Literal, Self

from pykit.check import CheckErr, check
from pykit.err import InpErr
from pykit.fcode import code
from pykit.query import Query
from rxcat import BaseModel, ErrEvt, Evt, Msg, OkEvt, Req, ServerBus

from orwynn.cfg import Cfg
from orwynn.dto import Dto, Udto
from orwynn.mongo import (
    CreateDocReq,
    DelDocReq,
    Doc,
    GetDocsReq,
    GotDocUdtosEvt,
    UpdDocReq,
    filter_collection_factory,
)
from orwynn.sys import Sys


class PermissionDto(Dto):
    code: str
    name: str
    dscr: str

@code("get-permission-dtos-req")
class GetPermissionDtosReq(Req):
    codes: list[str]

@code("got-permission-dtos-evt")
class GotPermissionDtosEvt(Evt):
    dtos: list[PermissionDto]

class PermissionModel(BaseModel):
    code: str
    name: str
    dscr: str

    @classmethod
    def to_dtos(cls, models: list[Self]) -> list[PermissionDto]:
        return [m.to_dto() for m in models]

    def to_dto(self) -> PermissionDto:
        return PermissionDto(
            code=self.code,
            name=self.name,
            dscr=self.dscr
        )

class RoleUdto(Udto):
    name: str
    dscr: str
    permissionCodes: list[str]
    isSuper: bool

class RoleDoc(Doc):
    name: str
    dscr: str
    permissionCodes: list[str] = []
    isSuper: bool = False
    """
    User with a super role ignore all permissions and can do whateva they want.
    """

    def to_udto(self) -> RoleUdto:
        return RoleUdto(
            sid=self.sid,
            name=self.name,
            dscr=self.dscr,
            permissionCodes=self.permissionCodes,
            isSuper=self.isSuper
        )

class RbacCfg(Cfg):
    permissions: list[PermissionModel] = []

class RoleSys(Sys):
    CommonSubMsgFilters = [
        filter_collection_factory(RoleDoc)
    ]

    async def enable(self):
        await self._sub(GetDocsReq, self._on_get_docs)
        await self._sub(CreateDocReq, self._on_create_doc)
        await self._sub(UpdDocReq, self._on_upd_doc)
        await self._sub(DelDocReq, self._on_del_doc)

    async def _on_get_docs(self, req: GetDocsReq):
        docs = list(RoleDoc.get_many(req.searchQuery))
        await self._pub(RoleDoc.to_got_doc_udtos_evt(req, docs))

    async def _on_create_doc(self, req: CreateDocReq):
        doc = RoleDoc(**req.createQuery).create()
        await self._pub(doc.to_got_doc_udto_evt(req))

    async def _on_upd_doc(self, req: UpdDocReq):
        doc = RoleDoc.get_and_upd(req.searchQuery, req.updQuery)
        await self._pub(doc.to_got_doc_udto_evt(req))

    async def _on_del_doc(self, req: DelDocReq):
        delf = RoleDoc.try_get_and_del(req.searchQuery)
        if delf:
            await self._pub(OkEvt(rsid="").as_res_from_req(req))

class PermissionSys(Sys):
    async def enable(self):
        await self._sub(GetPermissionDtosReq, self._on_get)

    async def _on_get(self, req: GetPermissionDtosReq):
        dtos = PermissionModel.to_dtos(
            RbacUtils.get_permissions_by_codes(req.codes)
        )
        await self._pub(GotPermissionDtosEvt(
            rsid="",
            dtos=dtos
        ).as_res_from_req(req))

class RbacUtils:
    _Permissions: list[PermissionModel] = []

    @classmethod
    def init(cls, cfg: RbacCfg):
        cls._Permissions = cfg.permissions.copy()

        # check duplicates
        codes: list[str] = []
        for p in cls._Permissions:
            if p.code in codes:
                raise InpErr(f"duplicate code {p.code}")
            codes.append(p.code)

    @classmethod
    async def req_get_roles_udto(
        cls,
        search_query: Query
    ) -> GotDocUdtosEvt | ErrEvt:
        f = None

        async def on(_, evt):
            nonlocal f
            f = evt

        req = GetDocsReq(
            collection=RoleDoc.get_collection(),
            searchQuery=search_query
        )
        await ServerBus.ie().pub(req, on)

        assert f
        return f

    @classmethod
    def get_permissions_by_codes(
        cls,
        codes: list[str]
    ) -> list[PermissionModel]:
        f = []
        if codes:
            for p in cls._Permissions:
                for c in codes:
                    if p.code == c:
                        f.append(p)
                        break
        else:
            # empty codes will search for everything
            f = cls._Permissions
        return f

    @classmethod
    def check_if_registered_permission_code(cls, permission_code: str):
        for permission in cls._Permissions:
            if permission.code == permission_code:
                return
        raise CheckErr(f"permission code {permission_code} is not registered")

    @classmethod
    def is_any_role_has_permission_to_pubsub_msg(
        cls,
        msg: Msg,
        roles: list[RoleUdto],
        msg_action: Literal["sub", "pub"]
    ) -> bool:
        permission_codes: set[str] = set()
        for role in roles:
            permission_codes.update(role.permissionCodes)

        for permission_code in permission_codes:
            cls.check_if_registered_permission_code(permission_code)
            if msg_action not in ["sub", "pub"]:
                raise InpErr(msg_action)

            permissions: dict[Literal["sub", "pub"], list[str]] | None = \
                getattr(
                    msg,
                    "Permissions",
                    None
                )
            if not permissions:
                return False
            check.instance(permissions, dict)

            action_permissions = permissions.get(msg_action, None)
            if not action_permissions:
                return False

            check.instance(action_permissions, list)
            return permission_code in action_permissions

        return False

class RbacSys(Sys[RbacCfg]):
    async def init(self):
        RbacUtils.init(self._cfg)

