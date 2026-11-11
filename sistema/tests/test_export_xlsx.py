import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bootstrap
import io
import sqlite3
import tempfile
import unittest
from datetime import date
from openpyxl import load_workbook
from app import create_app
from demo import create_demo
from export_xlsx import HEADERS, birth_and_age

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1])
        self.previous_tempdir = tempfile.tempdir
        tempfile.tempdir = self.temp.name
        self.path = Path(self.temp.name) / 'test.sqlite3'
        create_demo(self.path)
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                UPDATE clientes SET cpf='01234567890',nome='=1+1' WHERE id=1;
                UPDATE clientes SET excluido_em=CURRENT_TIMESTAMP WHERE id=3;
                INSERT INTO app_cliente_categorias (cliente_id,categoria_id) VALUES (1,1);
                INSERT INTO telefones (cliente_id,numero,excluido_em) VALUES (1,'11999999999',CURRENT_TIMESTAMP);
            """)
        db.close()
        self.app = create_app({'sqlite_path':str(self.path),'secret_key':'test','demo':True})
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self):
        tempfile.tempdir = self.previous_tempdir
        self.temp.cleanup()

    def login(self, role='demo'):
        self.client.get('/login')
        with self.client.session_transaction() as session:
            token=session['csrf']
        self.client.post('/login',data={'csrf':token,'login':role,'senha':'Demonstracao!2026'})

    def download(self, category='todos', **filters):
        response=self.client.get('/exportacoes/clientes.xlsx',query_string={'categoria':category, **filters})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        data=response.data
        response.close()
        workbook=load_workbook(io.BytesIO(data))
        rows=list(workbook.active.rows)
        workbook.close()
        self.assertEqual(tuple(cell.value for cell in rows[0]),HEADERS)
        count = self.client.get('/exportacoes/contagem',query_string={'categoria':category, **filters})
        self.assertEqual(count.status_code,200)
        self.assertEqual(count.json['total'],len(rows)-1)
        return rows[1:]

    def test_contents_filters_and_empty_export(self):
        self.login()
        self.assertEqual(self.client.get('/exportacoes').status_code,200)
        rows=self.download()
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0][0].value,'01234567890')
        self.assertEqual(rows[0][1].data_type,'s')
        self.assertEqual(rows[0][1].value,'=1+1')
        self.assertEqual(rows[0][2].value,'11000000000')
        self.assertEqual(rows[0][7].value,'00000000')
        self.assertIsNone(rows[1][12].value)
        self.assertEqual([cell.value for cell in rows[0][3:6]],[None,None,None])
        self.assertEqual([cell.value for cell in rows[1][2:6]],[None]*4)
        self.assertEqual(len(self.download('1')),1)
        self.assertEqual(self.download('sem')[0][0].value,'22222222222')
        self.assertEqual(len(self.download('2')),0)
        self.assertEqual(self.client.get('/exportacoes/clientes.xlsx?categoria=999').status_code,400)
        self.assertEqual(self.client.get('/exportacoes/clientes.xlsx?categoria=bad').status_code,400)

    def test_access(self):
        self.assertEqual(self.client.get('/exportacoes/clientes.xlsx').status_code,302)
        self.assertEqual(self.client.get('/exportacoes/contagem').status_code,302)
        self.login('atendimento')
        self.assertEqual(self.client.get('/exportacoes').status_code,403)
        self.assertEqual(self.client.get('/exportacoes/clientes.xlsx').status_code,403)
        self.assertEqual(self.client.get('/exportacoes/contagem').status_code,403)

    def test_four_phone_columns(self):
        self.login()
        with sqlite3.connect(self.path) as db:
            for number in ['01000000001','01000000002','01000000003','01000000004','01000000005']:
                db.execute('INSERT INTO telefones (cliente_id,numero) VALUES (1,?)',(number,))
            db.execute('INSERT INTO app_cliente_categorias (cliente_id,categoria_id) VALUES (1,2)')
        db.close()
        rows=self.download(categoria_id=['1','2'])
        self.assertEqual(len(rows),1)
        self.assertEqual([cell.value for cell in rows[0][2:6]],
                         ['11000000000','01000000001','01000000002','01000000003'])
        self.assertTrue(all(cell.data_type=='s' for cell in rows[0][2:6]))
        self.assertEqual(len(rows[0]),13)

    def test_consultation_filters(self):
        self.login()
        self.assertEqual(len(self.download(categoria_id=['1','2'])),1)
        self.assertEqual(len(self.download(categoria_id=['1','sem'])),2)
        self.assertEqual(len(self.download(uf='SP')),1)
        self.assertEqual(len(self.download(uf='RJ')),0)
        self.assertEqual(len(self.download(verificacao='com')),0)
        self.assertEqual(len(self.download(verificacao='sem')),2)
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE telefones SET situacao='confirmado' WHERE cliente_id=1 AND excluido_em IS NULL")
        db.close()
        self.assertEqual(len(self.download(categoria_id=['1'],uf='SP',verificacao='com')),1)
        self.assertEqual(len(self.download(categoria_id=['1'],verificacao='sem')),0)
        for query in ('uf=XX','verificacao=invalido','categoria_id=999'):
            self.assertEqual(self.client.get('/exportacoes/clientes.xlsx?'+query).status_code,400)

    def test_age(self):
        self.assertEqual(birth_and_age('2000-11-10',date(2026,11,9))[1],25)
        self.assertEqual(birth_and_age('2000-11-09',date(2026,11,9))[1],26)
        self.assertEqual(birth_and_age(None,date(2026,11,9)),(None,None))

if __name__ == '__main__':
    unittest.main()
