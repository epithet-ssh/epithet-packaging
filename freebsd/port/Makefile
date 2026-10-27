PORTNAME=	epithet
DISTVERSION=	0.0.0
PORTREVISION=	0
CATEGORIES=	security

MAINTAINER=	brianm@skife.org
COMMENT=	SSH certificate authorization and host enrollment
WWW=		https://github.com/epithet-ssh/epithet

LICENSE=	APACHE20
LICENSE_FILE=	${WRKSRC}/LICENSE-2.0.txt

USES=		go:1.26+,modules
USE_RC_SUBR=	epithet_server epithet_ca epithet_control epithet_directory epithet_inventory
# The publisher fills in an immutable source commit before makesum.
EPITHET_COMMIT=	UNSET
EPITHET_BUILD_DATE= UNSET
DISTNAME= epithet-${DISTVERSION}-${EPITHET_COMMIT}
# Supplied locally by the publisher, including vendor/. Never fetch by tag.
MASTER_SITES=
WRKSRC= ${WRKDIR}
GO_TARGET= ./cmd/epithet
GO_LDFLAGS= -X main.version=${DISTVERSION} -X main.commit=${EPITHET_COMMIT} -X main.date=${EPITHET_BUILD_DATE}
CGO_ENABLED=	0
# The pre-build check and all build/test commands must use this compiler.
GO_ENV+=	GOTOOLCHAIN=local

USERS=		epithet
GROUPS=		epithet
UID_FILES=	${FILESDIR}/UIDs ${PORTSDIR}/UIDs
GID_FILES=	${FILESDIR}/GIDs ${PORTSDIR}/GIDs

pre-build:
	cd ${WRKSRC} && ${SETENV} ${MAKE_ENV} ${GO_ENV} ${SH} ${FILESDIR}/go.sh ${GO_CMD} version

post-build:
	cd ${WRKSRC} && ${SETENV} ${MAKE_ENV} ${GO_ENV} GOPROXY=off ${GO_CMD} test ${GO_TESTFLAGS} ./...

post-install:
	${MKDIR} ${STAGEDIR}${ETCDIR}
.for service in server ca control directory inventory
	${INSTALL_DATA} ${FILESDIR}/${service}.toml.sample \
		${STAGEDIR}${ETCDIR}/${service}.toml.sample
.endfor

.include <bsd.port.mk>
