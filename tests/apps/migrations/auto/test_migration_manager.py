import asyncio
from unittest.mock import patch, MagicMock

from asyncpg.exceptions import UniqueViolationError
from piccolo.apps.migrations.auto import MigrationManager
from piccolo.apps.migrations.commands.base import BaseMigrationManager
from piccolo.columns import Varchar

from tests.example_project.tables import Manager
from tests.base import DBTestCase
from tests.base import postgres_only


class TestMigrationManager(DBTestCase):
    @postgres_only
    def test_rename_column(self):
        """
        Test running a MigrationManager which contains a column rename
        operation.
        """
        self.insert_row()

        manager = MigrationManager()
        manager.rename_column(
            table_class_name="Band",
            tablename="band",
            old_column_name="name",
            new_column_name="title",
        )
        asyncio.run(manager.run())

        response = self.run_sync("SELECT * FROM band;")
        self.assertTrue("title" in response[0].keys())
        self.assertTrue("name" not in response[0].keys())

        # Reverse
        asyncio.run(manager.run_backwards())
        response = self.run_sync("SELECT * FROM band;")
        self.assertTrue("title" not in response[0].keys())
        self.assertTrue("name" in response[0].keys())

    def test_raw_function(self):
        """
        Test adding raw functions to a MigrationManager.
        """

        class HasRun(Exception):
            pass

        def run():
            raise HasRun("I was run!")

        manager = MigrationManager()
        manager.add_raw(run)
        manager.add_raw_backwards(run)

        with self.assertRaises(HasRun):
            asyncio.run(manager.run())

        # Reverse
        with self.assertRaises(HasRun):
            asyncio.run(manager.run_backwards())

    def test_raw_coroutine(self):
        """
        Test adding raw coroutines to a MigrationManager.
        """

        class HasRun(Exception):
            pass

        async def run():
            raise HasRun("I was run!")

        manager = MigrationManager()
        manager.add_raw(run)
        manager.add_raw_backwards(run)

        with self.assertRaises(HasRun):
            asyncio.run(manager.run())

        # Reverse
        with self.assertRaises(HasRun):
            asyncio.run(manager.run_backwards())

    @postgres_only
    def test_add_table(self):
        """
        Test adding a table to a MigrationManager.
        """
        self.run_sync("DROP TABLE IF EXISTS musician;")

        manager = MigrationManager()
        name_column = Varchar()
        name_column._meta.name = "name"
        manager.add_table(
            class_name="Musician", tablename="musician", columns=[name_column]
        )
        asyncio.run(manager.run())

        self.run_sync("INSERT INTO musician VALUES (default, 'Bob Jones');")
        response = self.run_sync("SELECT * FROM musician;")

        self.assertEqual(response, [{"id": 1, "name": "Bob Jones"}])

        # Reverse
        asyncio.run(manager.run_backwards())
        self.assertEqual(self.table_exists("musician"), False)
        self.run_sync("DROP TABLE IF EXISTS musician;")

    @postgres_only
    def test_add_column(self):
        """
        Test adding a column to a MigrationManager.
        """
        manager = MigrationManager()
        manager.add_column(
            table_class_name="Manager",
            tablename="manager",
            column_name="email",
            column_class_name="Varchar",
            params={
                "length": 100,
                "default": "",
                "null": True,
                "primary": False,
                "key": False,
                "unique": True,
                "index": False,
            },
        )
        asyncio.run(manager.run())

        self.run_sync(
            "INSERT INTO manager VALUES (default, 'Dave', 'dave@me.com');"
        )

        response = self.run_sync("SELECT * FROM manager;")
        self.assertEqual(
            response, [{"id": 1, "name": "Dave", "email": "dave@me.com"}]
        )

        # Reverse
        asyncio.run(manager.run_backwards())
        response = self.run_sync("SELECT * FROM manager;")
        self.assertEqual(response, [{"id": 1, "name": "Dave"}])

    @postgres_only
    def test_add_non_nullable_column(self):
        """
        Test adding a non nullable column to a MigrationManager.

        Need to handle it gracefully if rows already exist.
        """
        self.run_sync("INSERT INTO manager VALUES (default, 'Dave');")

        manager = MigrationManager()
        manager.add_column(
            table_class_name="Manager",
            tablename="manager",
            column_name="email",
            column_class_name="Varchar",
            params={
                "length": 100,
                "default": "",
                "null": False,
                "primary": False,
                "key": False,
                "unique": True,
                "index": False,
            },
        )
        asyncio.run(manager.run())

    @postgres_only
    @patch.object(BaseMigrationManager, "get_migration_managers")
    def test_drop_column(self, get_migration_managers: MagicMock):
        """
        Test dropping a column with MigrationManager.
        """
        manager_1 = MigrationManager()
        name_column = Varchar()
        name_column._meta.name = "name"
        manager_1.add_table(
            class_name="Musician", tablename="musician", columns=[name_column]
        )
        asyncio.run(manager_1.run())

        self.run_sync("INSERT INTO musician VALUES (default, 'Dave');")
        response = self.run_sync("SELECT * FROM musician;")
        self.assertEqual(response, [{"id": 1, "name": "Dave"}])

        manager_2 = MigrationManager()
        manager_2.drop_column(
            table_class_name="Musician",
            tablename="musician",
            column_name="name",
        )
        asyncio.run(manager_2.run())

        response = self.run_sync("SELECT * FROM musician;")
        self.assertEqual(response, [{"id": 1}])

        # Reverse
        get_migration_managers.return_value = [manager_1]
        asyncio.run(manager_2.run_backwards())
        response = self.run_sync("SELECT * FROM musician;")
        self.assertEqual(response, [{"id": 1, "name": ""}])

    @postgres_only
    def test_rename_table(self):
        """
        Test renaming a table with MigrationManager.
        """
        manager = MigrationManager()

        manager.rename_table(
            old_class_name="Manager",
            old_tablename="manager",
            new_class_name="Director",
            new_tablename="director",
        )

        asyncio.run(manager.run())

        self.run_sync("INSERT INTO director VALUES (default, 'Dave');")

        response = self.run_sync("SELECT * FROM director;")
        self.assertEqual(response, [{"id": 1, "name": "Dave"}])

        # Reverse
        asyncio.run(manager.run_backwards())
        response = self.run_sync("SELECT * FROM manager;")
        self.assertEqual(response, [{"id": 1, "name": "Dave"}])

    @postgres_only
    def test_alter_column_unique(self):
        """
        Test altering a column uniqueness with MigrationManager.
        """
        manager = MigrationManager()

        manager.alter_column(
            table_class_name="Manager",
            tablename="manager",
            column_name="name",
            params={"unique": True},
            old_params={"unique": False},
        )

        asyncio.run(manager.run())

        with self.assertRaises(UniqueViolationError):
            self.run_sync(
                "INSERT INTO manager VALUES "
                "(default, 'Dave'), (default, 'Dave');"
            )

        # Reverse
        asyncio.run(manager.run_backwards())
        self.run_sync(
            "INSERT INTO manager VALUES (default, 'Dave'), (default, 'Dave');"
        )
        response = self.run_sync("SELECT name FROM manager;")
        self.assertEqual(response, [{"name": "Dave"}, {"name": "Dave"}])

    def _get_column_precision_and_scale(
        self, tablename="ticket", column_name="price"
    ):
        return self.run_sync(
            "SELECT numeric_precision, numeric_scale "
            "FROM information_schema.COLUMNS "
            f"WHERE table_name = '{tablename}' AND "
            f"column_name = '{column_name}';"
        )

    def _get_column_default(self, tablename="manager", column_name="name"):
        return self.run_sync(
            "SELECT column_default "
            "FROM information_schema.COLUMNS "
            f"WHERE table_name = '{tablename}' "
            f"AND column_name = '{column_name}';"
        )

    @postgres_only
    def test_alter_column_digits(self):
        """
        Test altering a column digits with MigrationManager.
        """
        manager = MigrationManager()

        manager.alter_column(
            table_class_name="Ticket",
            tablename="ticket",
            column_name="price",
            params={"digits": (6, 2)},
            old_params={"digits": (5, 2)},
        )

        asyncio.run(manager.run())
        self.assertEqual(
            self._get_column_precision_and_scale(),
            [{"numeric_precision": 6, "numeric_scale": 2}],
        )

        asyncio.run(manager.run_backwards())
        self.assertEqual(
            self._get_column_precision_and_scale(),
            [{"numeric_precision": 5, "numeric_scale": 2}],
        )

    @postgres_only
    def test_alter_column_set_default(self):
        """
        Test altering a column default with MigrationManager.
        """
        manager = MigrationManager()

        manager.alter_column(
            table_class_name="Manager",
            tablename="manager",
            column_name="name",
            params={"default": "Unknown"},
            old_params={"default": ""},
        )

        asyncio.run(manager.run())
        self.assertEqual(
            self._get_column_default(),
            [{"column_default": "'Unknown'::character varying"}],
        )

        asyncio.run(manager.run_backwards())
        self.assertEqual(
            self._get_column_default(),
            [{"column_default": "''::character varying"}],
        )

    @postgres_only
    def test_alter_column_add_index(self):
        """
        Test altering a column to add an index with MigrationManager.
        """
        manager = MigrationManager()

        manager.alter_column(
            table_class_name="Manager",
            tablename="manager",
            column_name="name",
            params={"index": True},
            old_params={"index": False},
        )

        asyncio.run(manager.run())
        self.assertTrue(
            Manager._get_index_name(["name"]) in Manager.indexes().run_sync()
        )

        asyncio.run(manager.run_backwards())
        self.assertTrue(
            Manager._get_index_name(["name"])
            not in Manager.indexes().run_sync()
        )

    @postgres_only
    @patch.object(BaseMigrationManager, "get_migration_managers")
    def test_drop_table(self, get_migration_managers: MagicMock):
        self.run_sync("DROP TABLE IF EXISTS musician;")

        name_column = Varchar()
        name_column._meta.name = "name"

        manager_1 = MigrationManager(migration_id="1", app_name="music")
        manager_1.add_table(
            class_name="Musician", tablename="musician", columns=[name_column]
        )
        asyncio.run(manager_1.run())

        manager_2 = MigrationManager(migration_id="2", app_name="music")
        manager_2.drop_table(class_name="Musician", tablename="musician")
        asyncio.run(manager_2.run())

        get_migration_managers.return_value = [manager_1]

        self.assertTrue(not self.table_exists("musician"))

        asyncio.run(manager_2.run_backwards())

        get_migration_managers.assert_called_with(
            app_name="music", max_migration_id="2", offset=-1
        )
        self.assertTrue(self.table_exists("musician"))

        self.run_sync("DROP TABLE IF EXISTS musician;")
