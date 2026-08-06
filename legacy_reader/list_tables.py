from access_connection import get_access_connection


def main():
    with get_access_connection() as connection:
        cursor = connection.cursor()

        objects = []

        for row in cursor.tables():
            name = row.table_name
            object_type = row.table_type

            if name and not name.startswith("MSys"):
                objects.append((object_type, name))

        objects.sort(key=lambda item: (item[0], item[1].lower()))

        print(f"{'TIPO':<20} | NOME")
        print("-" * 100)

        for object_type, name in objects:
            print(f"{object_type:<20} | {name}")

        print("-" * 100)
        print(f"Total: {len(objects)} objetos")


if __name__ == "__main__":
    main()