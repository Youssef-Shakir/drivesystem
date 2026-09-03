"""
Theme configuration for the Drive-Thru Intercom GUI.

Windows XP Luna Theme - Classic blue style
Edit colors here to customize the look and feel.
"""

# Windows XP Luna Blue Theme
COLORS = {
    # Backgrounds - XP classic colors
    'bg_primary': '#ECE9D8',      # XP tan/cream background
    'bg_secondary': '#D4D0C8',    # Classic gray
    'bg_card': '#FFFFFF',         # White panels
    'bg_hover': '#B6BDD2',        # Hover blue tint
    'bg_input': '#FFFFFF',        # Input field background

    # XP Blue accents
    'xp_blue_dark': '#0A246A',    # Dark title bar blue
    'xp_blue': '#0054E3',         # XP title bar blue
    'xp_blue_light': '#3169C6',   # Lighter blue
    'xp_blue_gradient_top': '#0058EE',
    'xp_blue_gradient_bottom': '#3A6EA5',

    # Accent colors
    'accent': '#CC0000',          # Red for alerts/warnings
    'accent_green': '#3C9A36',    # XP green (start button green)
    'accent_yellow': '#FFCC00',   # Warning yellow
    'accent_blue': '#0054E3',     # XP blue

    # Text
    'text_primary': '#000000',    # Black text
    'text_secondary': '#4A4A4A',  # Dark gray text
    'text_white': '#FFFFFF',      # White text for blue backgrounds
    'text_link': '#0066CC',       # Link blue

    # Borders - XP 3D style
    'border': '#808080',          # Standard border
    'border_light': '#FFFFFF',    # 3D highlight (top/left)
    'border_dark': '#404040',     # 3D shadow (bottom/right)
    'border_blue': '#0054E3',     # Blue border for focus

    # Status colors
    'status_online': '#00AA00',   # Green for online
    'status_offline': '#CC0000',  # Red for offline
    'status_warning': '#FF8800',  # Orange for warning
}


def get_stylesheet() -> str:
    """Get the main application stylesheet - Windows XP style."""
    return f"""
        QMainWindow {{
            background-color: {COLORS['bg_primary']};
        }}
        QWidget {{
            background-color: {COLORS['bg_primary']};
            color: {COLORS['text_primary']};
            font-family: "Tahoma", "Segoe UI", sans-serif;
            font-size: 11px;
        }}
        QScrollArea {{
            border: 2px inset {COLORS['border']};
            background-color: {COLORS['bg_card']};
        }}
        QTabWidget::pane {{
            border: 2px solid {COLORS['border']};
            background-color: {COLORS['bg_card']};
            margin-top: -2px;
        }}
        QTabBar::tab {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.4 #ECE9D8, stop:1 #D4D0C8);
            color: {COLORS['text_primary']};
            padding: 6px 16px;
            border: 1px solid {COLORS['border']};
            border-bottom: none;
            border-top-left-radius: 3px;
            border-top-right-radius: 3px;
            margin-right: 2px;
            min-width: 80px;
        }}
        QTabBar::tab:selected {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:1 #FFFFFF);
            border-bottom: 1px solid #FFFFFF;
            font-weight: bold;
        }}
        QTabBar::tab:hover:!selected {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:1 #D4D0FF);
        }}
        QGroupBox {{
            border: 2px groove {COLORS['border']};
            border-radius: 0px;
            margin-top: 12px;
            padding-top: 8px;
            background-color: {COLORS['bg_card']};
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            padding: 0 5px;
            background-color: {COLORS['bg_card']};
        }}
        QProgressBar {{
            border: 2px inset {COLORS['border']};
            background-color: {COLORS['bg_card']};
            text-align: center;
            height: 20px;
        }}
        QProgressBar::chunk {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #00FF00, stop:0.5 #00CC00, stop:1 #009900);
        }}
    """


def card_style() -> str:
    """Style for card/panel widgets - XP groupbox style."""
    return f"""
        background-color: {COLORS['bg_card']};
        border: 2px groove {COLORS['border']};
        padding: 8px;
    """


def xp_button_style(color: str = 'default') -> str:
    """Generate XP-style button."""
    if color == 'green':
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7FD37F, stop:0.4 #5ABF5A, stop:0.5 #3C9A36, stop:1 #2D7D2D);
                color: white;
                border: 2px outset #5ABF5A;
                border-radius: 3px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #8FE38F, stop:0.4 #6ACF6A, stop:0.5 #4CAA46, stop:1 #3D8D3D);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #2D7D2D, stop:0.5 #3C9A36, stop:1 #5ABF5A);
                border: 2px inset #3C9A36;
            }}
        """
    elif color == 'blue':
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #6699FF, stop:0.4 #3366DD, stop:0.5 #0054E3, stop:1 #003399);
                color: white;
                border: 2px outset #3366DD;
                border-radius: 3px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #77AAFF, stop:0.4 #4477EE, stop:0.5 #1065F4, stop:1 #1044AA);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #003399, stop:0.5 #0054E3, stop:1 #3366DD);
                border: 2px inset #0054E3;
            }}
        """
    elif color == 'red':
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF6666, stop:0.4 #DD3333, stop:0.5 #CC0000, stop:1 #990000);
                color: white;
                border: 2px outset #DD3333;
                border-radius: 3px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
                font-family: "Tahoma", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FF7777, stop:0.4 #EE4444, stop:0.5 #DD1111, stop:1 #AA0000);
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #990000, stop:0.5 #CC0000, stop:1 #DD3333);
                border: 2px inset #CC0000;
            }}
        """
    else:  # default gray XP button
        return f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
                color: {COLORS['text_primary']};
                border: 2px outset #D4D0C8;
                border-radius: 3px;
                padding: 6px 14px;
                font-size: 11px;
                font-family: "Tahoma", sans-serif;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:0.5 #D8D8F0, stop:1 #C0C0E0);
                border: 2px outset #8080C0;
            }}
            QPushButton:pressed {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #C8C8C8, stop:0.5 #E0E0E0, stop:1 #F0F0F0);
                border: 2px inset #D4D0C8;
            }}
        """


def xp_slider_style() -> str:
    """XP-style slider."""
    return f"""
        QSlider::groove:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #808080, stop:0.3 #C0C0C0, stop:1 #FFFFFF);
            height: 6px;
            border: 1px inset {COLORS['border']};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.4 #F0F0F0, stop:0.5 #E0E0E0, stop:1 #C8C8C8);
            width: 18px;
            margin: -6px 0;
            border: 2px outset #D4D0C8;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #FFFFFF, stop:0.4 #E8E8FF, stop:0.5 #D8D8F0, stop:1 #C0C0E0);
            border: 2px outset #8080C0;
        }}
        QSlider::sub-page:horizontal {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #0054E3, stop:0.5 #3169C6, stop:1 #6699FF);
            border: 1px solid #003399;
            border-radius: 3px;
        }}
    """


def xp_groupbox_style(title: str = "") -> str:
    """XP-style groupbox."""
    return f"""
        QGroupBox {{
            border: 2px groove {COLORS['border']};
            border-radius: 0px;
            margin-top: 14px;
            padding: 10px;
            padding-top: 14px;
            background-color: {COLORS['bg_card']};
            font-weight: bold;
            font-size: 11px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 8px;
            padding: 0 4px;
            background-color: {COLORS['bg_card']};
            color: {COLORS['xp_blue_dark']};
        }}
    """


def xp_title_bar_style() -> str:
    """XP-style title bar gradient."""
    return f"""
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #0058EE, stop:0.03 #3A6EA5, stop:0.08 #0054E3,
            stop:0.92 #0054E3, stop:0.97 #003399, stop:1 #002266);
        color: white;
        font-weight: bold;
        font-size: 14px;
        font-family: "Trebuchet MS", "Tahoma", sans-serif;
        padding: 6px 10px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    """


def xp_inset_panel_style() -> str:
    """XP-style inset panel (like text areas)."""
    return f"""
        background-color: {COLORS['bg_card']};
        border: 2px inset {COLORS['border']};
        padding: 4px;
    """


def xp_outset_panel_style() -> str:
    """XP-style raised panel."""
    return f"""
        background-color: {COLORS['bg_primary']};
        border: 2px outset {COLORS['border']};
        padding: 4px;
    """


def xp_status_badge_style(status: str = 'online') -> str:
    """XP-style status badge."""
    if status == 'online':
        bg = '#00CC00'
        border = '#009900'
    elif status == 'offline':
        bg = '#CC0000'
        border = '#990000'
    else:
        bg = '#FFCC00'
        border = '#CC9900'

    return f"""
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {bg}, stop:1 {border});
        color: white;
        padding: 3px 10px;
        border: 1px outset {border};
        border-radius: 2px;
        font-size: 10px;
        font-weight: bold;
        font-family: "Tahoma", sans-serif;
    """
