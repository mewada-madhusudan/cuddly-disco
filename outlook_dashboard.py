import sys
import time
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QPushButton, QFrame, QGridLayout,
                             QProgressBar, QScrollArea, QSplashScreen, QSpacerItem,
                             QSizePolicy)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QPixmap, QPainter

class LoadingWorker(QThread):
    """Worker thread for simulating loading process"""
    progress = pyqtSignal(int)
    finished = pyqtSignal()
    
    def run(self):
        for i in range(101):
            time.sleep(0.03)  # Simulate loading time
            self.progress.emit(i)
        self.finished.emit()

class CustomSplashScreen(QSplashScreen):
    def __init__(self):
        # Create a simple splash screen pixmap
        pixmap = QPixmap(400, 300)
        pixmap.fill(QColor(41, 128, 185))
        
        # Draw on the pixmap
        painter = QPainter(pixmap)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Arial", 24, QFont.Weight.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Outlook Assistant\nLoading...")
        painter.end()
        
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        
        # Setup progress bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setGeometry(50, 250, 300, 20)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid white;
                border-radius: 5px;
                text-align: center;
                color: white;
                background-color: rgba(255, 255, 255, 0.3);
            }
            QProgressBar::chunk {
                background-color: white;
                border-radius: 3px;
            }
        """)

class StatCard(QFrame):
    def __init__(self, title, value, change, icon_text, color="#2980b9"):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                padding: 15px;
            }}
        """)
        
        layout = QVBoxLayout()
        
        # Header with icon and title
        header_layout = QHBoxLayout()
        icon_label = QLabel(icon_text)
        icon_label.setStyleSheet(f"color: {color}; font-size: 18px; font-weight: bold;")
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #666; font-size: 12px;")
        
        header_layout.addWidget(icon_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        layout.addWidget(title_label)
        
        # Value
        value_label = QLabel(str(value))
        value_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #333; margin: 5px 0;")
        layout.addWidget(value_label)
        
        # Change indicator
        change_label = QLabel(change)
        change_label.setStyleSheet("color: #27ae60; font-size: 11px;")
        layout.addWidget(change_label)
        
        self.setLayout(layout)

class ActivityItem(QFrame):
    def __init__(self, title, time_ago, status_color="#27ae60"):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background-color: white;
                border: none;
                border-bottom: 1px solid #f0f0f0;
                padding: 10px;
            }
        """)
        
        layout = QHBoxLayout()
        
        # Status indicator
        status_dot = QLabel("●")
        status_dot.setStyleSheet(f"color: {status_color}; font-size: 16px;")
        
        # Content
        content_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; color: #333; font-size: 13px;")
        time_label = QLabel(time_ago)
        time_label.setStyleSheet("color: #999; font-size: 11px;")
        
        content_layout.addWidget(title_label)
        content_layout.addWidget(time_label)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(status_dot)
        layout.addLayout(content_layout)
        layout.addStretch()
        
        self.setLayout(layout)

class UsageBar(QFrame):
    def __init__(self, title, percentage):
        super().__init__()
        self.setStyleSheet("border: none;")
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 5, 0, 5)
        
        # Title and percentage
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #333; font-size: 13px;")
        percent_label = QLabel(f"{percentage}%")
        percent_label.setStyleSheet("color: #666; font-size: 13px; font-weight: bold;")
        
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(percent_label)
        
        # Progress bar
        progress = QProgressBar()
        progress.setMaximum(100)
        progress.setValue(percentage)
        progress.setTextVisible(False)
        progress.setFixedHeight(6)
        progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 3px;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #2c3e50;
                border-radius: 3px;
            }
        """)
        
        layout.addLayout(header_layout)
        layout.addWidget(progress)
        
        self.setLayout(layout)

class SidebarButton(QPushButton):
    def __init__(self, icon, text, active=False):
        super().__init__(f"{icon}  {text}")
        self.setFixedHeight(45)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        base_style = """
            QPushButton {
                text-align: left;
                padding: 0 15px;
                border: none;
                font-size: 13px;
                font-weight: 500;
                border-radius: 6px;
                margin: 2px 8px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.1);
            }
        """
        
        if active:
            self.setStyleSheet(base_style + """
                QPushButton {
                    background-color: #2980b9;
                    color: white;
                }
            """)
        else:
            self.setStyleSheet(base_style + """
                QPushButton {
                    color: #ecf0f1;
                    background-color: transparent;
                }
            """)

class OutlookDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Outlook Assistant - Professional Email Management")
        self.setGeometry(100, 100, 1200, 800)
        
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create sidebar and main content
        self.create_sidebar(main_layout)
        self.create_main_content(main_layout)
        
        # Apply main window styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f8f9fa;
            }
        """)

    def create_sidebar(self, parent_layout):
        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(260)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
            }
        """)
        
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 20, 0, 20)
        sidebar_layout.setSpacing(0)
        
        # Header
        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(15, 0, 15, 20)
        
        title_label = QLabel("Outlook Assistant")
        title_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        subtitle_label = QLabel("Professional Email Management")
        subtitle_label.setStyleSheet("color: #bdc3c7; font-size: 12px; margin-bottom: 10px;")
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        sidebar_layout.addLayout(header_layout)
        
        # Menu items
        menu_items = [
            ("🏠", "Dashboard", True),
            ("📧", "Send Email", False),
            ("📝", "Email Templates", False),
            ("📅", "Meeting Invite", False),
            ("🔧", "Legacy Functions", False),
            ("👥", "Contacts", False),
            ("📊", "Analytics", False),
            ("⚙️", "Settings", False)
        ]
        
        for icon, text, active in menu_items:
            btn = SidebarButton(icon, text, active)
            sidebar_layout.addWidget(btn)
        
        sidebar_layout.addStretch()
        
        # Pro tip section
        tip_frame = QFrame()
        tip_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(52, 152, 219, 0.2);
                border-radius: 8px;
                margin: 8px;
                padding: 15px;
            }
        """)
        
        tip_layout = QVBoxLayout(tip_frame)
        tip_title = QLabel("Pro Tip")
        tip_title.setStyleSheet("color: #3498db; font-weight: bold; font-size: 12px;")
        tip_text = QLabel("Use templates to save time on repetitive emails")
        tip_text.setStyleSheet("color: #ecf0f1; font-size: 11px;")
        tip_text.setWordWrap(True)
        
        tip_layout.addWidget(tip_title)
        tip_layout.addWidget(tip_text)
        sidebar_layout.addWidget(tip_frame)
        
        parent_layout.addWidget(sidebar)

    def create_main_content(self, parent_layout):
        # Main content area
        main_content = QWidget()
        main_layout = QVBoxLayout(main_content)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)
        
        # Header
        header = QVBoxLayout()
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #2c3e50; margin-bottom: 5px;")
        subtitle = QLabel("Welcome back! Here's your email management overview.")
        subtitle.setStyleSheet("color: #7f8c8d; font-size: 14px; margin-bottom: 15px;")
        
        header.addWidget(title)
        header.addWidget(subtitle)
        main_layout.addLayout(header)
        
        # Stats cards
        stats_layout = QGridLayout()
        stats_layout.setSpacing(20)
        
        stats_data = [
            ("Emails Sent Today", "24", "+12% from last week", "📧", "#3498db"),
            ("Templates Created", "12", "+12% from last week", "📝", "#27ae60"),
            ("Meetings Scheduled", "8", "+12% from last week", "📅", "#9b59b6"),
            ("Response Rate", "87%", "+12% from last week", "📈", "#e67e22")
        ]
        
        for i, (title, value, change, icon, color) in enumerate(stats_data):
            card = StatCard(title, value, change, icon, color)
            stats_layout.addWidget(card, i // 2, i % 2)
        
        main_layout.addLayout(stats_layout)
        
        # Bottom section with Recent Activity and Quick Actions
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(25)
        
        # Recent Activity
        activity_frame = QFrame()
        activity_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        
        activity_layout = QVBoxLayout(activity_frame)
        activity_layout.setContentsMargins(0, 0, 0, 0)
        
        activity_header = QLabel("Recent Activity")
        activity_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; padding: 20px 20px 10px;")
        activity_subtitle = QLabel("Latest actions in your Outlook Assistant")
        activity_subtitle.setStyleSheet("color: #7f8c8d; font-size: 12px; padding: 0 20px 15px;")
        
        activity_layout.addWidget(activity_header)
        activity_layout.addWidget(activity_subtitle)
        
        activities = [
            ("Email sent to Marketing Team", "2 minutes ago", "#27ae60"),
            ("Meeting invite sent to John Doe", "15 minutes ago", "#27ae60"),
            ("Template 'Weekly Report' created", "1 hour ago", "#27ae60"),
            ("Legacy function executed", "2 hours ago", "#f39c12")
        ]
        
        for title, time_ago, color in activities:
            activity_item = ActivityItem(title, time_ago, color)
            activity_layout.addWidget(activity_item)
        
        activity_layout.addStretch()
        
        # Quick Actions
        actions_frame = QFrame()
        actions_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
            }
        """)
        
        actions_layout = QVBoxLayout(actions_frame)
        actions_layout.setContentsMargins(20, 20, 20, 20)
        
        actions_header = QLabel("Quick Actions")
        actions_header.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50; margin-bottom: 5px;")
        actions_subtitle = QLabel("Frequently used features")
        actions_subtitle.setStyleSheet("color: #7f8c8d; font-size: 12px; margin-bottom: 20px;")
        
        actions_layout.addWidget(actions_header)
        actions_layout.addWidget(actions_subtitle)
        
        usage_data = [
            ("Email Templates Usage", 75),
            ("Meeting Scheduling", 60),
            ("Response Tracking", 90)
        ]
        
        for title, percentage in usage_data:
            usage_bar = UsageBar(title, percentage)
            actions_layout.addWidget(usage_bar)
        
        actions_layout.addStretch()
        
        bottom_layout.addWidget(activity_frame)
        bottom_layout.addWidget(actions_frame)
        
        main_layout.addLayout(bottom_layout)
        main_layout.addStretch()
        
        parent_layout.addWidget(main_content)

def main():
    app = QApplication(sys.argv)
    
    # Create and show splash screen
    splash = CustomSplashScreen()
    splash.show()
    
    # Create loading worker
    worker = LoadingWorker()
    
    def update_progress(value):
        splash.progress_bar.setValue(value)
        splash.showMessage(f"Loading... {value}%", Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignCenter, QColor(255, 255, 255))
    
    def loading_finished():
        splash.finish(window)
        window.show()
    
    worker.progress.connect(update_progress)
    worker.finished.connect(loading_finished)
    
    # Create main window (but don't show it yet)
    window = OutlookDashboard()
    
    # Start loading
    worker.start()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()