# Troca o perfil ativo do G604 (1 = Padrao, 2 = Vava). Nao grava nada na memoria.
import sys, os, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import G604
n = int(sys.argv[1])
nomes = {1: 'Padrao', 2: 'Vava'}
try:
    m = G604()
    m.set_profile(n)
    ok = m.get_profile()[1] == n
    msg = f'Mouse no perfil {nomes[n]}' if ok else 'Nao consegui confirmar a troca'
except Exception as e:
    msg = f'Erro ao trocar perfil: {e}\n(O mouse esta ligado? G Hub/OMM fechados?)'
ctypes.windll.user32.MessageBoxW(0, msg, 'G604', 0x40 | 0x40000)
