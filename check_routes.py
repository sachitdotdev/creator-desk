from app.api.routes import router

for route in router.routes:
    if route.method == 'POST':
        print(f'{route.method} {route.path}')