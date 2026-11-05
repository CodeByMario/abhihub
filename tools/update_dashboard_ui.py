path = 'templates/p_index.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update button styling in p_index.html
old_btn_styles = """.deck-btn-primary {
    background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
    color: #ffffff !important;
    border: none;
    border-radius: 10px;
    padding: 0.65rem 1.25rem;
    font-size: 0.9rem;
    font-weight: 700;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35);
  }
  .deck-btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.5);
  }
  .deck-btn-gold {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: #ffffff !important;
    border: none;
    border-radius: 10px;
    padding: 0.65rem 1.25rem;
    font-size: 0.9rem;
    font-weight: 700;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(217, 119, 6, 0.35);
  }
  .deck-btn-gold:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(217, 119, 6, 0.5);
  }
  .deck-btn-hollow {
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: #ffffff !important;
    border-radius: 10px;
    padding: 0.65rem 1.15rem;
    font-size: 0.9rem;
    font-weight: 600;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s ease;
    cursor: pointer;
  }
  .deck-btn-hollow:hover {
    background: rgba(255, 255, 255, 0.16);
    border-color: rgba(255, 255, 255, 0.3);
    transform: translateY(-1px);
  }"""

new_btn_styles = """.deck-btn-primary {
    background: #0071E3;
    color: #ffffff !important;
    border: none;
    border-radius: 980px;
    min-height: 44px;
    padding: 0.65rem 1.45rem;
    font-size: 0.9rem;
    font-weight: 600;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
    box-shadow: 0 4px 14px rgba(0, 113, 227, 0.3);
  }
  .deck-btn-primary:hover {
    background: #0077ED;
    transform: scale(1.02);
    box-shadow: 0 6px 20px rgba(0, 113, 227, 0.4);
  }
  .deck-btn-gold {
    background: rgba(255, 255, 255, 0.12);
    border: 1.5px solid rgba(255, 255, 255, 0.28);
    color: #ffffff !important;
    border-radius: 980px;
    min-height: 44px;
    padding: 0.65rem 1.4rem;
    font-size: 0.9rem;
    font-weight: 600;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
    backdrop-filter: blur(8px);
  }
  .deck-btn-gold:hover {
    background: rgba(255, 255, 255, 0.22);
    border-color: rgba(255, 255, 255, 0.45);
    transform: scale(1.02);
  }
  .deck-btn-hollow {
    background: transparent;
    border: 1.5px solid rgba(255, 255, 255, 0.2);
    color: #ffffff !important;
    border-radius: 980px;
    min-height: 44px;
    padding: 0.65rem 1.3rem;
    font-size: 0.9rem;
    font-weight: 600;
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    cursor: pointer;
  }
  .deck-btn-hollow:hover {
    background: rgba(255, 255, 255, 0.12);
    border-color: rgba(255, 255, 255, 0.4);
    transform: scale(1.02);
  }"""

text = text.replace(old_btn_styles.replace('\n', '\r\n'), new_btn_styles.replace('\n', '\r\n'))
text = text.replace(old_btn_styles, new_btn_styles)

with open(path, 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated p_index.html buttons successfully")
