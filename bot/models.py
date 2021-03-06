from typing import List, Optional, Dict, Union
from datetime import datetime, timedelta
import bot

ResumeID = str
"""Идентификатор резюме на hh.ru."""

UserID = int
"""Идентификатор пользователя Telegram."""


class HeadHunterResume:
    """Резюме на hh.ru."""

    resume_id: ResumeID
    """Идентификатор резюме."""

    title: str
    """Название резюме."""

    status: str
    """Статус резюме."""

    next_publish_at: datetime
    """Время, когда резюме можно будет поднять в поиске в следующий раз."""

    access: str
    """Доступ к резюме для других пользователей hh.ru."""

    user_id: UserID = None
    """Идентификатор пользователя."""

    is_active: bool = False
    """Активно ли резюме."""

    until: datetime = None
    """До какого срока активно резюме."""

    def __init__(
            self,
            resume_id: ResumeID,
            title: str,
            status: str,
            next_publish_at: datetime,
            access: str,
            user_id: UserID=None,
            is_active: bool=False,
            until: datetime=None
    ):
        self.resume_id = resume_id
        self.title = title
        self.status = status
        self.next_publish_at = next_publish_at
        self.access = access
        self.user_id = user_id
        self.is_active = is_active
        self.until = until

    def as_dict(self):
        return dict(
            resume_id=self.resume_id,
            title=self.title,
            status=self.status,
            next_publish_at=self.next_publish_at,
            access=self.access,
            user_id=self.user_id,
            is_active=self.is_active,
            until=self.until
        )

    @staticmethod
    async def create_table() -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info("Models: Creating table 'public.resume'...")
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public.resume
                    (
                        resume_id character varying(64) COLLATE pg_catalog."default" NOT NULL,
                        user_id bigint NOT NULL,
                        title character varying(128) COLLATE pg_catalog."default" NOT NULL,
                        status character varying(64) COLLATE pg_catalog."default" NOT NULL,
                        next_publish_at timestamp with time zone NOT NULL,
                        access character varying(64) COLLATE pg_catalog."default" NOT NULL,
                        is_active boolean NOT NULL DEFAULT false,
                        until timestamp with time zone NOT NULL,
                        CONSTRAINT resume_pkey PRIMARY KEY (resume_id),
                        CONSTRAINT fk_resume_user_id FOREIGN KEY (user_id)
                            REFERENCES public."user" (user_id) MATCH SIMPLE
                            ON UPDATE NO ACTION
                            ON DELETE CASCADE
                    )
                    WITH (
                        OIDS = FALSE
                    )
                    TABLESPACE pg_default;

                    ALTER TABLE public.resume
                        OWNER to postgres;
                    """
                )

    async def create(self) -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f"Models: Inserting resume {self.resume_id}...")

                await cur.execute(
                    """
                    INSERT INTO
                        public.resume
                        (resume_id, title, status, next_publish_at, access, user_id, is_active, until)
                    VALUES
                        (
                            %(resume_id)s,
                            %(title)s,
                            %(status)s,
                            %(next_publish_at)s,
                            %(access)s,
                            %(user_id)s,
                            %(is_active)s,
                            %(until)s
                        );
                    """,
                    self.as_dict()
                )

    @staticmethod
    async def get(resume_id: ResumeID) -> Optional['HeadHunterResume']:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Getting resume with id {resume_id}...')
                await cur.execute(
                    """
                    SELECT
                        resume_id,
                        user_id,
                        title,
                        status,
                        next_publish_at,
                        access,
                        is_active,
                        until
                    FROM
                        public.resume
                    WHERE
                        resume_id = %(resume_id)s;
                    """,
                    {'resume_id': resume_id}
                )
                resume = await cur.fetchone()
                if not resume:
                    return None
                return HeadHunterResume(
                    resume_id=resume[0],
                    user_id=resume[1],
                    title=resume[2],
                    status=resume[3],
                    next_publish_at=resume[4],
                    access=resume[5],
                    is_active=resume[6],
                    until=resume[7]
                )

    async def update(self) -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Updating resume with id {self.resume_id}...')
                await cur.execute(
                    """
                    UPDATE
                        public.resume
                    SET
                        user_id=%(user_id)s,
                        title=%(title)s,
                        status=%(status)s,
                        next_publish_at=%(next_publish_at)s,
                        access=%(access)s,
                        is_active=%(is_active)s,
                        until=%(until)s
                    WHERE
                        resume_id = %(resume_id)s;
                    """,
                    self.as_dict()
                )

    async def upsert(self) -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Inserting or updating resume with id {self.resume_id}...')
                await cur.execute(
                    """
                    UPDATE
                        public.resume
                    SET
                        user_id=%(user_id)s,
                        title=%(title)s,
                        status=%(status)s,
                        next_publish_at=%(next_publish_at)s,
                        access=%(access)s,
                        is_active=%(is_active)s,
                        until=%(until)s
                    WHERE resume_id=%(resume_id)s;
                    
                    INSERT INTO
                        public.resume
                        (resume_id, title, status, next_publish_at, access, user_id, is_active, until)
                        SELECT
                            %(resume_id)s,
                            %(title)s,
                            %(status)s,
                            %(next_publish_at)s,
                            %(access)s,
                            %(user_id)s,
                            %(is_active)s,
                            %(until)s
                        WHERE NOT EXISTS (
                            SELECT
                                1
                            FROM
                                public.resume
                            WHERE
                                resume_id=%(resume_id)s
                        );
                    """,
                    self.as_dict()
                )

    async def activate(self) -> None:
        bot.log.info(f'Models: Activating resume with id {self.resume_id}...')
        self.is_active = True
        self.until = datetime.now() + timedelta(days=7)
        await self.upsert()

    async def deactivate(self) -> None:
        bot.log.info(f'Models: Deactivating resume with id {self.resume_id}...')
        self.is_active = False
        await self.update()

    @staticmethod
    async def get_user_active_resume_list(user: 'TelegramUser') -> List['HeadHunterResume']:
        assert user.user_id

        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT
                        resume_id,
                        user_id,
                        title,
                        status,
                        next_publish_at,
                        access,
                        is_active,
                        until
                    FROM
                        public.resume
                    WHERE
                        user_id=%(user_id)s AND
                        is_active;
                    """,
                    {
                        'user_id': user.user_id
                    }
                )

                resumes = await cur.fetchall()
                return [
                    HeadHunterResume(
                        resume_id=r[0],
                        user_id=r[1],
                        title=r[2],
                        status=r[3],
                        next_publish_at=r[4],
                        access=r[5],
                        is_active=r[6],
                        until=r[7]
                    )
                    for r in resumes
                ]

    @staticmethod
    async def get_active_resume_list() -> Dict[UserID, List[Dict[str, Union['HeadHunterResume', 'TelegramUser']]]]:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Getting active resume list...')
                await cur.execute(
                    """
                    SELECT
                        public.resume.resume_id,  -- 0
                        public.resume.title,      -- 1
                        public.resume.status,     -- 2
                        public.resume.next_publish_at,  -- 3
                        public.resume.access,     -- 4
                        public.resume.until,      -- 5
                        public.user.user_id       -- 6
                        public.user.hh_token      -- 7
                    FROM
                        public.resume
                    JOIN
                        public.user ON public.user.user_id = public.resume.user_id
                    WHERE
                        active;
                    """
                )

                resumes_and_users = {}

                for r in await cur.fetchall():
                    user_id = r[6]
                    if user_id not in resumes_and_users:
                        resumes_and_users[user_id] = []

                    resumes_and_users[user_id].append(
                        {
                            'resume': HeadHunterResume(
                                resume_id=r[0],
                                title=r[1],
                                status=r[2],
                                next_publish_at=r[3],
                                access=r[4],
                                until=r[5]
                            ),
                            'user': TelegramUser(
                                user_id=user_id,
                                hh_token=r[7]
                            )
                        }
                    )

                return resumes_and_users


class TelegramUser:
    """Пользователь бота в Telegram."""

    user_id: UserID
    """Идентификатор пользователя в Telegram."""

    hh_token: str = None
    """Токен для доступа к API hh.ru."""

    first_name: str = None
    """Имя пользователя (берется из данных пользователя на hh.ru)."""

    last_name: str = None
    """Фамилия пользователя (берется из данных пользователя на hh.ru)."""

    email: str = None
    """Адрес электронной почты (берется из данных пользователя на hh.ru)."""

    is_waiting_for_token: bool = True
    """Состояние: ожидается ли от пользователя токен в следующем сообщении."""

    def __init__(
            self,
            user_id: UserID,
            hh_token: str=None,
            first_name: str=None,
            last_name: str=None,
            email: str=None,
            is_waiting_for_token: bool=True
    ):
        self.user_id = user_id
        self.hh_token = hh_token
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.is_waiting_for_token = is_waiting_for_token

    def as_dict(self):
        return dict(
            user_id=self.user_id,
            hh_token=self.hh_token,
            first_name=self.first_name,
            last_name=self.last_name,
            email=self.email,
            is_waiting_for_token=self.is_waiting_for_token
        )

    @staticmethod
    async def create_table() -> None:
        """Метод для создания таблицы в БД."""
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info("Models: Creating table 'public.user'...")
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS public."user"
                    (
                        user_id bigint NOT NULL,
                        hh_token character varying(64) COLLATE pg_catalog."default",
                        first_name character varying(64) COLLATE pg_catalog."default",
                        last_name character varying(64) COLLATE pg_catalog."default",
                        email character varying(64) COLLATE pg_catalog."default",
                        is_waiting_for_token boolean NOT NULL DEFAULT true,
                        CONSTRAINT user_pkey PRIMARY KEY (user_id)
                    )
                    WITH (
                        OIDS = FALSE
                    )
                    TABLESPACE pg_default;

                    ALTER TABLE public."user"
                        OWNER to postgres;
                    """
                )

    async def create(self) -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Creating user with id {self.user_id}...')
                await cur.execute(
                    """
                    INSERT INTO
                        public.user
                        (user_id, hh_token, first_name, last_name, email, is_waiting_for_token)
                    VALUES
                    (
                        %(user_id)s,
                        %(hh_token)s,
                        %(first_name)s,
                        %(last_name)s,
                        %(email)s,
                        %(is_waiting_for_token)s
                    );
                    """,
                    self.as_dict()
                )

    @staticmethod
    async def get(user_id: UserID) -> Optional['TelegramUser']:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f'Models: Getting user with id {user_id}...')
                await cur.execute(
                    """
                    SELECT
                        user_id,
                        hh_token,
                        first_name,
                        last_name,
                        email,
                        is_waiting_for_token
                    FROM
                        public.user
                    WHERE
                        user_id = %(user_id)s;
                    """,
                    {'user_id': user_id}
                )
                user = await cur.fetchone()
                if not user:
                    return None
                return TelegramUser(
                    user_id=user[0],
                    hh_token=user[1],
                    first_name=user[2],
                    last_name=user[3],
                    email=user[4],
                    is_waiting_for_token=user[5]
                )

    async def update(self) -> None:
        async with bot.pg_pool.acquire() as conn:
            async with conn.cursor() as cur:
                bot.log.info(f"Models: Updating user with id {self.user_id}...")

                await cur.execute(
                    """
                    UPDATE
                        public.user
                    SET
                        hh_token=%(hh_token)s,
                        first_name=%(first_name)s,
                        last_name=%(last_name)s,
                        email=%(email)s,
                        is_waiting_for_token=%(is_waiting_for_token)s
                    WHERE
                        user_id=%(user_id)s;
                    """,
                    self.as_dict()
                )
