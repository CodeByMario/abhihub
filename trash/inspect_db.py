from methods.supabase_helper import init_supabase

def inspect():
    client = init_supabase()
    
    # Just fetch one row from each to see the columns
    c = client.table('colleges').select('*').limit(1).execute()
    print("Colleges:", c.data[0].keys() if c.data else "Empty")
    
    d = client.table('departments').select('*').limit(1).execute()
    print("Departments:", d.data[0].keys() if d.data else "Empty")
    
    cd = client.table('college_departments').select('*').limit(1).execute()
    print("College_Departments:", cd.data[0].keys() if cd.data else "Empty")
    
    s = client.table('subjects').select('*').limit(1).execute()
    print("Subjects:", s.data[0].keys() if s.data else "Empty")

if __name__ == "__main__":
    inspect()
