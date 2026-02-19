
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

try:
    print("Checking database_repositories.py...")
    from database_repositories import UnifiedJobRepository
    print("✅ UnifiedJobRepository class found.")
    
    try:
        from database_repositories import DashboardRepository
        print("⚠️ WARNING: DashboardRepository class still exists (should be removed or deprecated).")
    except ImportError:
        print("✅ DashboardRepository class is correctly removed/hidden.")

    print("\nChecking web_server.py imports...")
    # We don't import web_server directly as it might start the app, 
    # but we can check if it compiles.
    import py_compile
    py_compile.compile('web_server.py', cfile='web_server.pyc', doraise=True)
    print("✅ web_server.py syntax is valid.")

    print("\nDeep Check Complete.")

except Exception as e:
    print(f"❌ Verification Failed: {e}")
    sys.exit(1)
