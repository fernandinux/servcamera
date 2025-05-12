mi_diccionario = {"clave_dinam123ica": "valor"}

# Obtener la única clave
clave = next(iter(mi_diccionario))
valor = mi_diccionario[clave]

print(f"Clave: {clave}, Valor: {valor}")