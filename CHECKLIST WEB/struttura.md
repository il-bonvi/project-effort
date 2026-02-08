bFactor/
├── PEFFORT/                    # ✓ NO CHANGES
│   ├── inspection_web_gui.py   # Riuso diretto
│   ├── map3d_gui.py
│   ├── pplan_gui.py
│   └── ...
│
├── webapp/                     # 🆕 MINIMAL
│   └── app.py                  # FastAPI single file
│
├── templates/                  # 🆕 (opzionale - se vuoi template Jinja)
│   └── base.html
│
├── uploads/                    # 🆕 Temp storage
│
└── requirements.txt            # FastAPI + esistenti