-- ============================================================
-- AbhiHub Migration 014: Leaderboard View
-- ============================================================

-- Create a view to instantly aggregate XP for the leaderboard
DROP VIEW IF EXISTS abhihub.leaderboard_view;

CREATE VIEW abhihub.leaderboard_view AS
SELECT 
    p.id AS user_id,
    p.full_name,
    p.email,
    p.college_id,
    COALESCE(p.reputation_score, 0) + COALESCE(SUM(c.xp_awarded), 0) AS total_xp,
    p.students_helped
FROM 
    abhihub.profiles p
LEFT JOIN 
    abhihub.contribution_logs c ON p.id = c.user_id
GROUP BY 
    p.id, p.full_name, p.email, p.college_id, p.students_helped
ORDER BY 
    total_xp DESC;
