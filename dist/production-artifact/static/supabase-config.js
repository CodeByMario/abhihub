import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.39.0/+esm';

// Supabase configuration
// SECURITY NOTE: The anon key below is intentionally public and designed to be exposed in client-side code.
// It is protected by Row Level Security (RLS) policies in Supabase, which control data access at the database level.
// Ensure all your Supabase tables have proper RLS policies enabled to prevent unauthorized access.
const SUPABASE_URL = 'https://xchqudjccefnykpuzhxd.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhjaHF1ZGpjY2VmbnlrcHV6aHhkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDk5MzEyODEsImV4cCI6MjA2NTUwNzI4MX0.OH9jAZ492x-Ui-8f_L6gChRcB_YpnalgCCF2XMeopfI';

// Initialize Supabase client with implicit flow for OAuth
// Implicit flow returns access_token in URL hash instead of requiring code exchange
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
        flowType: 'implicit' // Use implicit flow for simpler OAuth handling
    },
    db: {
        schema: 'abhihub'
    }
});

export { supabase };
