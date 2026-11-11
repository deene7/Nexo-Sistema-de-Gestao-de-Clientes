"""Exportação de clientes em lotes, preservando identificadores como texto."""
from datetime import date, datetime, timedelta, timezone
from tempfile import SpooledTemporaryFile

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font

from database import Database

HEADERS = ('cpf', 'nome', 'telefone_1', 'telefone_2', 'telefone_3', 'telefone_4', 'email', 'cep', 'cidade', 'estado',
           'data_nascimento', 'genero', 'idade')


def birth_and_age(value, today):
    try:
        birth = date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None, None
    if birth > today:
        return birth, None
    return birth, today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def build_clients_workbook(config, where, params):
    today = datetime.now(timezone(timedelta(hours=-3))).date()
    workbook = Workbook(write_only=True)
    output = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
    connection = Database(config)
    count = 0

    def new_sheet():
        sheet = workbook.create_sheet('Clientes' if not workbook.worksheets else f'Clientes {len(workbook.worksheets)+1}')
        sheet.freeze_panes = 'A2'
        for column, width in zip('ABCDEFGHIJKLM', (16, 40, 18, 18, 18, 18, 40, 12, 25, 12, 20, 16, 10)):
            sheet.column_dimensions[column].width = width
        cells = [WriteOnlyCell(sheet, value=name) for name in HEADERS]
        for cell in cells:
            cell.font = Font(bold=True)
        sheet.append(cells)
        return sheet

    try:
        connection.execute('BEGIN' if connection.sqlite else 'START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
        sheet = new_sheet()
        last_id = 0
        while True:
            clients = connection.all('SELECT c.id,c.cpf,c.nome,c.data_nascimento,c.sexo_origem '
                                     f'FROM clientes c WHERE ({where}) AND c.id>%s ORDER BY c.id LIMIT 1000',
                                     list(params) + [last_id])
            if not clients:
                break
            ids = [client['id'] for client in clients]
            marks = ','.join(['%s'] * len(ids))
            phones, emails, addresses = {}, {}, {}
            # Limita os contatos no banco antes de transferir o lote para o Python.
            for item in connection.all(
                    f'SELECT cliente_id,numero FROM (SELECT cliente_id,numero,id, '
                    f'ROW_NUMBER() OVER (PARTITION BY cliente_id ORDER BY id) AS pos '
                    f'FROM telefones WHERE cliente_id IN ({marks}) AND excluido_em IS NULL) ranked '
                    'WHERE pos<=4 ORDER BY cliente_id,id', ids):
                phones.setdefault(item['cliente_id'], []).append(item['numero'] or '')
            for item in connection.all(f'SELECT cliente_id,email FROM emails WHERE cliente_id IN ({marks}) AND excluido_em IS NULL ORDER BY id', ids):
                emails.setdefault(item['cliente_id'], []).append(item['email'] or '')
            for item in connection.all(
                    f'SELECT cliente_id,cep,cidade,uf FROM (SELECT cliente_id,cep,cidade,uf, '
                    f'ROW_NUMBER() OVER (PARTITION BY cliente_id ORDER BY id) AS pos '
                    f'FROM enderecos WHERE cliente_id IN ({marks}) AND excluido_em IS NULL) ranked WHERE pos=1', ids):
                addresses.setdefault(item['cliente_id'], item)
            for client in clients:
                if count and count % 1048575 == 0:
                    sheet.auto_filter.ref = 'A1:M1048576'
                    sheet = new_sheet()
                key = client['id']
                address = addresses.get(key, {})
                birth, age = birth_and_age(client['data_nascimento'], today)
                numbers = phones.get(key, [])[:4]
                numbers += [None] * (4 - len(numbers))
                values = [client['cpf'], client['nome'], *numbers,
                          ' | '.join(emails.get(key, [])), address.get('cep'), address.get('cidade'),
                          address.get('uf'), birth, client['sexo_origem'], age]
                cells = []
                for value in values:
                    cell = WriteOnlyCell(sheet, value=value)
                    if isinstance(value, str):
                        cell.data_type = 's'
                        cell.number_format = '@'
                    elif isinstance(value, date):
                        cell.number_format = 'dd/mm/yyyy'
                    cells.append(cell)
                sheet.append(cells)
                count += 1
            last_id = clients[-1]['id']
        sheet.auto_filter.ref = f'A1:M{((count-1) % 1048575)+2 if count else 1}'
        workbook.save(output)
        output.seek(0)
        return output, count
    except Exception:
        output.close()
        raise
    finally:
        workbook.close()
        connection.rollback()
        connection.close()
