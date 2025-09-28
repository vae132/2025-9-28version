#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import shutil
import threading
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QPushButton, QLabel, QMessageBox, QFrame,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QComboBox
)
from PyQt5.QtGui import QFont, QIcon, QIntValidator
from PyQt5.QtCore import Qt, pyqtSignal

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.executors.pool import ThreadPoolExecutor as APSchedulerThreadPoolExecutor
from apscheduler.jobstores.memory import MemoryJobStore

# 导入爬虫模块
import CrawlAll      # 旧的全量爬虫
import crawler       # 新的增量更新爬虫（crawler.py）
import generator     # 网页生成模块

# 简单邮箱格式校验正则
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailConfigDialog(QDialog):
    """
    配置定时发送邮件的对话框，支持常见服务商快速填充和自定义。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("配置邮件定时发送")
        self.setModal(True)
        self.resize(800, 600)
        self.setMinimumSize(800, 600)
        font = QFont('Arial', 14)
        self.setFont(font)

        layout = QFormLayout(self)
        layout.setLabelAlignment(Qt.AlignRight)
        layout.setFormAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # 服务商下拉框
        self.provider_combo = QComboBox()
        self.provider_combo.setFont(font)
        self.provider_combo.addItem("自定义")
        self.provider_combo.addItem("QQ 邮箱 (smtp.qq.com:587)")
        self.provider_combo.addItem("腾讯企业邮箱 (smtp.exmail.qq.com:465)")
        self.provider_combo.currentIndexChanged.connect(self.on_provider_changed)
        layout.addRow("服务商:", self.provider_combo)

        def make_line_edit(placeholder, tooltip):
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setToolTip(tooltip)
            le.setFont(font)
            le.setMinimumHeight(35)
            le.setMinimumWidth(450)
            return le

        self.smtp_edit      = make_line_edit("如 smtp.example.com", "SMTP 服务器地址，例如 smtp.example.com")
        self.port_edit      = make_line_edit("如 587",           "SMTP 端口号，通常为 25、465 或 587")
        self.port_edit.setValidator(QIntValidator(1, 65535, self))

        self.sender_edit    = make_line_edit("如 sender@example.com", "发件人邮箱地址，例如 yourname@qq.com")
        self.password_edit  = make_line_edit("邮箱授权码/密码",        "邮箱 SMTP 授权码或登录密码")
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.recipient_edit = make_line_edit("如 receiver@example.com","收件人邮箱地址")
        self.interval_edit  = make_line_edit("分钟，例如 60",         "发送间隔，单位分钟(1-10080)")
        self.interval_edit.setValidator(QIntValidator(1, 10080, self))
        self.file_edit      = make_line_edit("如 index.html 或 /path/to/index.html",
                                             "要发送的文件路径，确保文件存在")
        self.subject_edit   = make_line_edit("如 自动发送网页",       "邮件主题")

        layout.addRow("SMTP 服务器:",    self.smtp_edit)
        layout.addRow("端口:",           self.port_edit)
        layout.addRow("发件人 Email:",   self.sender_edit)
        layout.addRow("密码:",           self.password_edit)
        layout.addRow("收件人 Email:",   self.recipient_edit)
        layout.addRow("发送间隔 (分钟):", self.interval_edit)
        layout.addRow("文件路径:",       self.file_edit)
        layout.addRow("邮件主题:",       self.subject_edit)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.button(QDialogButtonBox.Ok).setText("确认")
        btn_box.button(QDialogButtonBox.Cancel).setText("取消")
        btn_box.setFont(font)
        btn_box.setMinimumHeight(50)
        btn_box.accepted.connect(self.on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def on_provider_changed(self, index):
        if index == 1:
            self.smtp_edit.setText("smtp.qq.com")
            self.port_edit.setText("587")
            self.smtp_edit.setEnabled(False)
            self.port_edit.setEnabled(False)
        elif index == 2:
            self.smtp_edit.setText("smtp.exmail.qq.com")
            self.port_edit.setText("465")
            self.smtp_edit.setEnabled(False)
            self.port_edit.setEnabled(False)
        else:
            self.smtp_edit.clear()
            self.port_edit.clear()
            self.smtp_edit.setEnabled(True)
            self.port_edit.setEnabled(True)

    def on_accept(self):
        cfg = self.get_config()
        errors = []
        if not cfg['smtp_server']:
            errors.append("SMTP 服务器不能为空。")
        if not cfg['port'].isdigit():
            errors.append("端口必须为数字。")
        if not EMAIL_REGEX.match(cfg['sender']):
            errors.append("发件人邮箱格式不正确。")
        if not cfg['password']:
            errors.append("SMTP 授权码/密码不能为空。")
        if not EMAIL_REGEX.match(cfg['recipient']):
            errors.append("收件人邮箱格式不正确。")
        if not cfg['interval'].isdigit():
            errors.append("发送间隔必须为数字。")
        if not cfg['file'] or not os.path.exists(cfg['file']):
            errors.append("文件路径不存在或为空。")
        if not cfg['subject']:
            errors.append("邮件主题不能为空。")
        if errors:
            QMessageBox.critical(self, "输入错误", "\n".join(errors), QMessageBox.Ok)
            return
        self.accept()

    def get_config(self):
        return {
            'smtp_server': self.smtp_edit.text().strip(),
            'port':        self.port_edit.text().strip(),
            'sender':      self.sender_edit.text().strip(),
            'password':    self.password_edit.text(),
            'recipient':   self.recipient_edit.text().strip(),
            'interval':    self.interval_edit.text().strip(),
            'file':        self.file_edit.text().strip(),
            'subject':     self.subject_edit.text().strip()
        }


class MainWindow(QMainWindow):
    status_updated = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("阳气诊所 管理控制台")
        self.resize(1600, 900)
        self.setMinimumSize(1200, 800)
        self.setWindowIcon(QIcon())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout()
        layout.setSpacing(40)
        layout.setContentsMargins(80, 50, 80, 50)
        central.setLayout(layout)

        title = QLabel("☯ 阳气诊所 后台管理")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont('Arial', 36, QFont.Bold))
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setFixedHeight(4)
        layout.addWidget(line)

        self.status_label = QLabel("状态：等待操作")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setFont(QFont('Arial', 18))
        layout.addWidget(self.status_label)
        self.status_updated.connect(self.status_label.setText)

        btn_font = QFont('Arial', 20)
        buttons = [
            ("🕷️ 爬取所有评论",     self.crawl_comments),
            ("📝 根据 data 数据生成网页", self.generate_html),
            ("🔄 更新最新留言并生成网页", self.update_and_generate),
            ("⏰ 启动定时每天12点更新",  self.start_schedule),
            ("📧 配置定时发送网页邮件",  self.open_email_config),
        ]
        for text, handler in buttons:
            btn = QPushButton(text)
            btn.setFont(btn_font)
            btn.setFixedHeight(100)
            btn.clicked.connect(handler)
            layout.addWidget(btn)

        self.scheduler = BackgroundScheduler(
            executors={'default': APSchedulerThreadPoolExecutor(max_workers=4)},
            jobstores={'default': MemoryJobStore()},
            job_defaults={'coalesce': False, 'max_instances': 1, 'misfire_grace_time': 3600}
        )
        self.scheduler.start()
        self.scheduled = False

    def crawl_comments(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("确认爬取方式")
        msg.setText("是否删除以前的数据并重新爬取？")
        msg.setInformativeText(
            "● 是：删除旧数据，重新从头爬取\n"
            "● 否：继续上次断点续爬"
        )
        msg.setIcon(QMessageBox.Question)
        msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg.setDefaultButton(QMessageBox.No)
        msg.setFont(QFont('Arial', 16))
        msg.setMinimumSize(600, 300)
        reply = msg.exec_()
        reset = (reply == QMessageBox.Yes)

        def task(do_reset):
            if do_reset:
                self.status_updated.emit("状态：正在删除旧数据…")
                try:
                    if os.path.exists("datatest"):
                        shutil.rmtree("datatest")
                    prog_file = getattr(CrawlAll, "PROGRESS_FILE", "progress.txt")
                    if os.path.exists(prog_file):
                        os.remove(prog_file)
                    self.status_updated.emit("状态：✔ 历史数据已删除，开始重新爬取")
                except Exception as e:
                    self.status_updated.emit(f"状态：✖ 删除失败: {e}")
            else:
                self.status_updated.emit("状态：从上次进度继续爬取…")

            try:
                CrawlAll.crawl()
                self.status_updated.emit("状态：✔ 评论爬取完成")
            except Exception as e:
                self.status_updated.emit(f"状态：✖ 爬取失败: {e}")

        threading.Thread(target=task, args=(reset,), daemon=True).start()

    def generate_html(self):
        def task():
            self.status_updated.emit("状态：正在根据本地 data 生成网页…")
            try:
                generator.main()
                self.status_updated.emit("状态：✔ 网页生成完成")
            except Exception as e:
                self.status_updated.emit(f"状态：✖ 生成失败: {e}")
        threading.Thread(target=task, daemon=True).start()

    def update_and_generate(self):
        def task():
            self.status_updated.emit("状态：正在更新最新留言并生成网页…")
            try:
                # 调用 crawler.py 中的主更新流程
                crawler.main_update()
                # 然后再生成最新的网页
                generator.main()
                self.status_updated.emit("状态：✔ 更新并生成完成")
            except Exception as e:
                self.status_updated.emit(f"状态：✖ 更新失败: {e}")
        threading.Thread(target=task, daemon=True).start()

    def start_schedule(self):
        if self.scheduled:
            QMessageBox.information(self, "提示", "定时任务已启动：每天中午12点自动更新。", QMessageBox.Ok)
            return
        self.scheduler.add_job(self.update_and_generate, 'cron', hour=12, minute=0, id='daily_update')
        self.scheduled = True
        QMessageBox.information(self, "提示", "已启动定时更新：每天中午12点自动更新并生成网页。", QMessageBox.Ok)

    def open_email_config(self):
        dlg = EmailConfigDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            cfg = dlg.get_config()
            try:
                self.scheduler.remove_job('email_job')
            except:
                pass
            self.scheduler.add_job(
                self.send_email_job,
                'interval',
                minutes=int(cfg['interval']),
                id='email_job',
                args=[cfg]
            )
            QMessageBox.information(self, "设置完成", f"每 {cfg['interval']} 分钟发送一次邮件。", QMessageBox.Ok)

    def send_email_job(self, cfg):
        generator.main()
        filepath = cfg.get('file', 'index.html')
        try:
            msg = MIMEMultipart()
            msg['Subject'] = cfg['subject']
            msg['From']    = cfg['sender']
            msg['To']      = cfg['recipient']
            with open(filepath, 'rb') as f:
                part = MIMEApplication(f.read(), _subtype='html')
                part.add_header('Content-Disposition', 'attachment', filename=os.path.basename(filepath))
                msg.attach(part)
            smtp = smtplib.SMTP(cfg['smtp_server'], int(cfg['port']))
            smtp.starttls()
            smtp.login(cfg['sender'], cfg['password'])
            smtp.send_message(msg)
            smtp.quit()
            self.status_updated.emit("状态：✔ 邮件发送成功")
        except Exception as e:
            self.status_updated.emit(f"状态：✖ 邮件发送失败: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setFont(QFont('Arial', 16))
    app.setStyleSheet("""
        QMainWindow { background-color: #f0f0f5; }
        QPushButton { background-color: #667eea; color: white; border-radius: 12px; }
        QPushButton:hover { background-color: #556cd6; }
        QLabel { color: #333333; }
        QFrame { background-color: #cccccc; }
    """)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
