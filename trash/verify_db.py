from methods.supabase_helper import init_supabase

def test():
    client = init_supabase()
    
    docs = client.table('documents').select('id', count='exact').execute()
    print("Total documents in Supabase:", docs.count)
    
    ranks = client.table('profiles').select('full_name, reputation_score').order('reputation_score', desc=True).limit(5).execute()
    print("Top 5 Profiles:")
    for r in ranks.data:
        print(r)

if __name__ == "__main__":
    test()
