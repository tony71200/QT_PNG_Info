from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QLabel,
    QFileDialog, QHBoxLayout, QVBoxLayout, QTextEdit, QCheckBox,
    QListWidget, QListWidgetItem, QSplitter, QSizePolicy, QFrame, QTreeWidgetItem,
    QLineEdit, QGridLayout
)
from PyQt5.QtGui import QIcon, QPixmap, QDragEnterEvent, QDropEvent, QTextCursor, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QEvent
import sys
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
import re

class ImageDropLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.image_dropped_callback = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        image_paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path) and any(path.lower().endswith(ext) for ext in image_extensions):
                image_paths.append(path)
        if image_paths and self.image_dropped_callback:
            self.image_dropped_callback(image_paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Prompt Manager")
        self.setGeometry(100, 100, 1000, 700)

        self.folder_path = ""
        self.current_image_path = ""
        self.current_pixmap = QPixmap()

        self.init_ui()
        self.statusBar().showMessage("Ready")

    def init_ui(self):
        # Widget trung tâm
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # Layout chính
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)

        # Layout cho thanh chọn thư mục
        folder_layout = QHBoxLayout()

        self.btn_browse = QPushButton("Open Folder")
        self.btn_browse.setIcon(QIcon.fromTheme("folder"))
        # self.btn_browse.setFixedSize(32, 32)
        self.btn_browse.clicked.connect(self.choose_folder)

        self.lbl_folder = QLabel("Chưa chọn thư mục")
        self.lbl_folder.setStyleSheet("font-weight: bold; color: #FFFFFF; background-color: #333333; padding: 5px;")
        self.lbl_folder.setTextInteractionFlags(Qt.TextSelectableByMouse)

        folder_layout.addWidget(self.btn_browse)
        folder_layout.addWidget(self.lbl_folder)

        # Split panel chính chia làm 2: Trái (ảnh) - Phải (prompt)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # ----- KHU HÌNH ẢNH (TRÁI) -----
        image_widget = QWidget()
        image_layout = QVBoxLayout()
        image_widget.setLayout(image_layout)
        image_widget.setMinimumWidth(400)

        self.lbl_image = ImageDropLabel("Kéo ảnh vào đây hoặc chọn từ danh sách")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setFrameShape(QFrame.Box)
        self.lbl_image.setMinimumHeight(400)
        self.lbl_image.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.lbl_image.image_dropped_callback = self.handle_dropped_images
        self.lbl_image.installEventFilter(self)

        self.list_images = QListWidget()
        self.list_images.setMinimumHeight(180)
        self.list_images.setViewMode(QListWidget.IconMode)
        self.list_images.setIconSize(QSize(100, 100))
        self.list_images.setResizeMode(QListWidget.Adjust)
        self.list_images.setMovement(QListWidget.Static)
        self.list_images.setSpacing(8)
        self.list_images.setUniformItemSizes(True)
        self.list_images.itemClicked.connect(self.display_selected_image)

        image_layout.addWidget(self.lbl_image, 3)
        image_layout.addWidget(self.list_images, 1)

        # ----- KHU PROMPT (PHẢI) -----
        # Tab Layout cho Prompt
        from PyQt5.QtWidgets import QTabWidget, QTreeWidget, QTreeWidgetItem
        self.tab_prompt = QTabWidget()
        self.tab_prompt.setMinimumWidth(300)

        # Tab Content (chỉ đọc metadata)
        self.tab_content = QWidget()
        content_layout = QVBoxLayout()
        self.tab_content.setLayout(content_layout)
        self.tree_metadata = QTreeWidget()
        self.tree_metadata.setHeaderLabels(["Keyword", "Content"])
        self.tree_metadata.setColumnCount(2)
        self.tree_metadata.setRootIsDecorated(False)
        self.tree_metadata.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.tree_metadata.setWordWrap(True)
        content_layout.addWidget(self.tree_metadata)

        # Tab Edit (giữ layout cũ)
        self.tab_edit = QWidget()
        edit_layout = QVBoxLayout()
        self.tab_edit.setLayout(edit_layout)
        self.txt_positive = QTextEdit()
        self.txt_positive.setPlaceholderText("Positive Prompt (e.g. masterpiece, 8k, detailed)")
        self.txt_negative = QTextEdit()
        self.txt_negative.setPlaceholderText("Negative Prompt (e.g. low quality, blurry)")
        replace_widget = QWidget()
        replace_layout = QGridLayout()
        replace_widget.setLayout(replace_layout)
        replace_layout.setColumnStretch(0, 1)
        replace_layout.setColumnStretch(1, 1)
        self.txt_find = QLineEdit()
        self.txt_find.setPlaceholderText("Find text")
        self.txt_replace = QLineEdit()
        self.txt_replace.setPlaceholderText("Replace with")
        self.btn_find = QPushButton("Find")
        self.btn_find.clicked.connect(self.find_in_prompts)
        self.btn_replace = QPushButton("Replace")
        self.btn_replace.clicked.connect(self.replace_in_prompts)
        self.btn_replace_all = QPushButton("Replace All")
        self.btn_replace_all.clicked.connect(self.replace_all_in_prompts)
        replace_layout.addWidget(self.txt_find, 0, 0, 1, 2)
        replace_layout.addWidget(self.btn_find, 0, 2)
        replace_layout.addWidget(self.txt_replace, 1, 0, 1, 2)
        replace_layout.addWidget(self.btn_replace, 1, 2)
        replace_layout.addWidget(self.btn_replace_all, 2, 0, 1, 3)
        self.chk_autosave = QCheckBox("Auto Save")
        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_prompt_file)
        edit_layout.addWidget(self.txt_positive)
        edit_layout.addWidget(self.txt_negative)
        edit_layout.addWidget(replace_widget)
        edit_layout.addWidget(self.chk_autosave)
        edit_layout.addWidget(self.btn_save)

        self.tab_prompt.addTab(self.tab_content, "Content")
        self.tab_prompt.addTab(self.tab_edit, "Edit")

        # Thêm vào splitter
        self.main_splitter.addWidget(image_widget)
        self.main_splitter.addWidget(self.tab_prompt)
        self.main_splitter.setSizes([600, 400])
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 0)

        # Đặt tỉ lệ cho layout
        main_layout.addLayout(folder_layout, 0)
        main_layout.addWidget(self.main_splitter, 1)

    def choose_folder(self):
        initial_dir = self.folder_path if os.path.isdir(self.folder_path) else os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa ảnh", initial_dir)
        if folder:
            self.folder_path = folder
            self.lbl_folder.setText(folder)
            self.load_images_from_folder(folder)

    def load_images_from_folder(self, folder):
        self.list_images.clear()
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']

        image_files = [f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)]
        image_files.sort()
        metrics = QFontMetrics(self.list_images.font())

        for file in image_files:
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            display_name = metrics.elidedText(file, Qt.ElideMiddle, 140)
            item = QListWidgetItem(icon, display_name)
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(file)
            self.list_images.addItem(item)

        if self.list_images.count() > 0:
            self.list_images.setCurrentRow(0)
            self.display_selected_image(self.list_images.item(0))

    def display_selected_image(self, item):
        if self.chk_autosave.isChecked():
            self.save_prompt_file()

        image_path = item.data(Qt.UserRole)
        self.display_image_from_path(image_path)
        self.load_prompt_file(image_path)
        self.load_metadata_content(image_path)

    def display_image_from_path(self, path):
        self.current_image_path = path
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            self.current_pixmap = pixmap
            self.update_image_display()
            self.statusBar().showMessage(path)
        else:
            self.current_pixmap = QPixmap()
            self.lbl_image.setText("Không thể hiển thị ảnh")
            self.statusBar().showMessage("Không thể hiển thị ảnh")

    def update_image_display(self):
        if not self.current_pixmap.isNull() and not self.lbl_image.size().isEmpty():
            scaled = self.current_pixmap.scaled(
                self.lbl_image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.lbl_image.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_image_display()

    def eventFilter(self, obj, event):
        if obj == self.lbl_image and event.type() == QEvent.Resize:
            self.update_image_display()
        return super().eventFilter(obj, event)

    def load_prompt_file(self, image_path):
        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        if os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                # Nếu đúng format cũ: <positive>###<negative>###size
                parts = content.split("###")
                if len(parts) >= 2:
                    self.txt_positive.setText(parts[0])
                    self.txt_negative.setText(parts[1])
        elif os.path.exists(image_path):
            from PIL import Image
            import PIL
            meta_text = None
            try:
                img = Image.open(image_path)
                info = img.info
                # PNG: metadata thường nằm trong info['parameters'] hoặc info['Description'] hoặc info['prompt']
                for k in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                    if k in info and isinstance(info[k], str) and len(info[k]) > 10:
                        meta_text = info[k]
                        break
                # JPEG: metadata có thể nằm trong EXIF (UserComment, ImageDescription...)
                if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            decoded = PIL.ExifTags.TAGS.get(tag, tag)
                            if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                                meta_text = value
                                break
            except Exception as e:
                meta_text = None
            # Nếu không đúng format, tìm positive/negative prompt trong metadata
            meta = self.parse_metadata(meta_text) if meta_text else {}
            self.txt_positive.setText(meta.get("Positive prompt", ""))
            self.txt_negative.setText(meta.get("Negative prompt", ""))
        else:
            self.txt_positive.clear()
            self.txt_negative.clear()

    def _find_in_text_edit(self, text_edit, query):
        if not query:
            return False
        original_cursor = text_edit.textCursor()
        cursor = text_edit.textCursor()
        cursor.movePosition(QTextCursor.Start)
        text_edit.setTextCursor(cursor)
        found = text_edit.find(query)
        if not found:
            text_edit.setTextCursor(original_cursor)
            return False
        text_edit.setFocus()
        return True

    def find_in_prompts(self):
        query = self.txt_find.text().strip()
        if not query:
            self.statusBar().showMessage("Nhập nội dung cần tìm")
            return
        if self._find_in_text_edit(self.txt_positive, query):
            self.tab_prompt.setCurrentWidget(self.tab_edit)
            self.statusBar().showMessage("Đã tìm thấy trong Positive Prompt")
            return
        if self._find_in_text_edit(self.txt_negative, query):
            self.tab_prompt.setCurrentWidget(self.tab_edit)
            self.statusBar().showMessage("Đã tìm thấy trong Negative Prompt")
            return
        self.statusBar().showMessage("Không tìm thấy nội dung cần tìm")

    def replace_in_prompts(self):
        find_text = self.txt_find.text().strip()
        replace_text = self.txt_replace.text()
        if not find_text:
            self.statusBar().showMessage("Nhập nội dung cần thay thế")
            return
        replaced = False
        for text_edit in (self.txt_positive, self.txt_negative):
            content = text_edit.toPlainText()
            if find_text in content:
                new_content = content.replace(find_text, replace_text)
                if new_content != content:
                    text_edit.blockSignals(True)
                    text_edit.setPlainText(new_content)
                    text_edit.blockSignals(False)
                    replaced = True
        if replaced:
            self.statusBar().showMessage("Đã thay thế nội dung")
            if self.chk_autosave.isChecked():
                self.save_prompt_file()
        else:
            self.statusBar().showMessage("Không tìm thấy nội dung để thay thế")

    def replace_all_in_prompts(self):
        find_text = self.txt_find.text().strip()
        replace_text = self.txt_replace.text()
        if not find_text:
            self.statusBar().showMessage("Nhập nội dung cần thay thế")
            return
        if not self.folder_path or self.list_images.count() == 0:
            self.statusBar().showMessage("Chưa có thư mục hoặc ảnh để thay thế")
            return

        replacements = 0
        for idx in range(self.list_images.count()):
            item = self.list_images.item(idx)
            if not item:
                continue
            image_path = item.data(Qt.UserRole)
            positive, negative, size_str = self._read_prompt_data(image_path)
            original_positive = positive or ""
            original_negative = negative or ""
            new_positive = original_positive.replace(find_text, replace_text)
            new_negative = original_negative.replace(find_text, replace_text)
            if new_positive != original_positive or new_negative != original_negative:
                self._write_prompt_file(image_path, new_positive, new_negative, size_str)
                replacements += 1
                if image_path == self.current_image_path:
                    self.txt_positive.blockSignals(True)
                    self.txt_positive.setPlainText(new_positive)
                    self.txt_positive.blockSignals(False)
                    self.txt_negative.blockSignals(True)
                    self.txt_negative.setPlainText(new_negative)
                    self.txt_negative.blockSignals(False)

        if replacements:
            self.statusBar().showMessage(f"Đã thay thế trong {replacements} ảnh")
        else:
            self.statusBar().showMessage("Không tìm thấy nội dung để thay thế trong thư mục")

    def _normalize_prompt_text(self, text):
        if not text:
            return ""
        parts = [segment.strip() for segment in text.split("\n") if segment.strip()]
        if not parts:
            return ""
        return " ".join(parts)

    def _size_string_from_dimensions(self, width, height):
        if not width or not height:
            return "832x1216"
        if width > height:
            return "1216x832"
        if width < height:
            return "832x1216"
        return "1024x1024"

    def _infer_size_from_image(self, image_path):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return "832x1216"
        return self._size_string_from_dimensions(pixmap.width(), pixmap.height())

    def _read_prompt_data(self, image_path):
        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        positive = ""
        negative = ""
        size_str = None
        if os.path.exists(prompt_path):
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                parts = content.split("###")
                if parts:
                    positive = parts[0].strip()
                if len(parts) > 1:
                    negative = parts[1].strip()
                if len(parts) > 2 and parts[2].strip():
                    size_str = parts[2].strip()
            except Exception:
                positive = negative = ""
                size_str = None
        else:
            meta_text = None
            try:
                from PIL import Image
                import PIL
                img = Image.open(image_path)
                info = img.info
                for k in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                    if k in info and isinstance(info[k], str) and len(info[k]) > 10:
                        meta_text = info[k]
                        break
                if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            decoded = PIL.ExifTags.TAGS.get(tag, tag)
                            if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                                meta_text = value
                                break
            except Exception:
                meta_text = None
            if meta_text:
                meta = self.parse_metadata(meta_text)
                positive = meta.get("Positive prompt", "")
                negative = meta.get("Negative prompt", "")
                size_str = meta.get("Size")

        if not size_str:
            size_str = self._infer_size_from_image(image_path)
        return positive, negative, size_str

    def _write_prompt_file(self, image_path, positive, negative, size_str):
        prompt_path = os.path.splitext(image_path)[0] + ".txt"
        positive_text = self._normalize_prompt_text(positive)
        negative_text = self._normalize_prompt_text(negative)

        if not positive_text:
            positive_text = "1boy, 1 man"
        if not negative_text:
            negative_text = "(1girl, woman, female)"
        if not size_str:
            size_str = self._infer_size_from_image(image_path)

        content = f"{positive_text}###{negative_text}###{size_str}"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(content)

    def load_metadata_content(self, image_path):
        # Đọc metadata trực tiếp từ file ảnh (PNG/JPG)
        from PIL import Image
        import PIL
        import textwrap
        self.tree_metadata.clear()
        meta_text = None
        try:
            img = Image.open(image_path)
            info = img.info
            # PNG: metadata thường nằm trong info['parameters'] hoặc info['Description'] hoặc info['prompt']
            for k in ['parameters', 'Description', 'prompt', 'Comment', 'Software']:
                if k in info and isinstance(info[k], str) and len(info[k]) > 10:
                    meta_text = info[k]
                    break
            # JPEG: metadata có thể nằm trong EXIF (UserComment, ImageDescription...)
            if meta_text is None and hasattr(img, '_getexif') and img._getexif():
                exif = img._getexif()
                if exif:
                    for tag, value in exif.items():
                        decoded = PIL.ExifTags.TAGS.get(tag, tag)
                        if decoded in ['UserComment', 'ImageDescription', 'XPComment', 'XPSubject'] and isinstance(value, str) and len(value) > 10:
                            meta_text = value
                            break
        except Exception as e:
            meta_text = None
        if not meta_text:
            # Không có metadata
            return
        meta = self.parse_metadata(meta_text)
        wrap_len = 80  # Số ký tự tối đa mỗi dòng
        for key in [
            "Positive prompt", "Negative prompt", "Steps", "Sampler", "Schedule type", "CFG scale", "Seed", "Face restoration", "Size", "Width", "Height", "Model hash", "Model", "Clip skip", "Token merging ratio", "Lora hash", "Other", "Version"]:
            val = meta.get(key, "")
            if val:
                # Tự động wrapped nếu quá dài
                if isinstance(val, str) and len(val) > wrap_len:
                    val = '\n'.join(textwrap.wrap(val, wrap_len))
                item = QTreeWidgetItem([key, val])
                self.tree_metadata.addTopLevelItem(item)

    def parse_metadata(self, content):
        if not content:
            return {}
        blocks = re.split(r"(?:\r?\n){2,}", content.strip())
        selected_meta = {}
        for block in blocks:
            meta, has_tony = self.parse_block(block)
            if meta:
                if has_tony:
                    return meta
                if not selected_meta:
                    selected_meta = meta
        return selected_meta

    def parse_block(self, block):
        technical_fields = [
            r"Steps\s*:\s*\d+",
            r"Sampler\s*:\s*[^,\n]+",
            r"CFG scale\s*:\s*[^,\n]+",
            r"Size\s*:\s*\d+[xX×]\d+",
            r"Seed\s*:\s*\d+",
            r"Model\s*:\s*[^,\n]+",
            r"Width\s*:\s*\d+",
            r"Height\s*:\s*\d+"
        ]
        tech_pattern = re.compile(r"|".join(technical_fields), re.IGNORECASE)

        lines = [line.strip() for line in block.strip().split("\n") if line.strip()]
        if not lines:
            return {}, False

        prompt_lines, negative_lines = [], []
        tech_data = {}
        in_negative = False
        width = height = seed = None
        size_str = None
        has_tony = any(line.lower().endswith("tony") for line in lines)
        field_map = {
            "steps": "Steps",
            "sampler": "Sampler",
            "cfg scale": "CFG scale",
            "size": "Size",
            "seed": "Seed",
            "model": "Model",
            "width": "Width",
            "height": "Height"
        }

        for line in lines:
            lower_line = line.lower()
            if lower_line.startswith("negative prompt:"):
                in_negative = True
                negative_lines.append(line.split(":", 1)[1].strip())
                continue
            if in_negative:
                if tech_pattern.search(line):
                    in_negative = False
                else:
                    negative_lines.append(line)
                    continue
            if tech_pattern.search(line):
                segments = [seg.strip() for seg in re.split(r",\s*(?=[^:,]+:\s*)", line) if seg.strip()]
                for segment in segments:
                    if not re.search(r":", segment):
                        continue
                    parts = segment.split(":", 1)
                    key_raw = parts[0].strip()
                    value = parts[1].strip().strip(",")
                    canonical = field_map.get(key_raw.lower(), key_raw)
                    tech_data[canonical] = value
                    m = re.search(r"Width\s*:\s*(\d+)", segment, re.IGNORECASE)
                    if m:
                        width = int(m.group(1))
                    m = re.search(r"Height\s*:\s*(\d+)", segment, re.IGNORECASE)
                    if m:
                        height = int(m.group(1))
                    m = re.search(r"Size\s*:\s*(\d+)[xX×](\d+)", segment, re.IGNORECASE)
                    if m:
                        width = int(m.group(1))
                        height = int(m.group(2))
                    m = re.search(r"Seed\s*:\s*(\d+)", segment, re.IGNORECASE)
                    if m:
                        seed = int(m.group(1))
                continue
            if not lower_line.startswith("negative prompt:"):
                prompt_lines.append(line)

        prompt = " ".join(prompt_lines).replace("  ", " ").replace(" , ", ", ").strip()
        negative_prompt = " ".join(negative_lines).replace("  ", " ").replace(" , ", ",").strip()
        if not negative_prompt:
            negative_prompt = "(1girl, female, woman, vagina,pussy,vaginal,clitoris, beard)"

        if width and height:
            if width > height:
                size_str = "1216x832"
            elif width < height:
                size_str = "832x1216"
            else:
                size_str = "1024x1024"
        else:
            size_str = "832x1216"
        seed_val = seed if seed is not None else -1

        meta = {
            "Positive prompt": prompt,
            "Negative prompt": negative_prompt,
            "Size": size_str,
            "Seed": str(seed_val)
        }
        for key in ("Steps", "Sampler", "CFG scale", "Model", "Width", "Height"):
            if key in tech_data:
                meta[key] = tech_data[key]
        if "Width" not in meta and width:
            meta["Width"] = str(width)
        if "Height" not in meta and height:
            meta["Height"] = str(height)
        return meta, has_tony

    def save_prompt_file(self):
        if not self.current_image_path:
            return

        positive = self.txt_positive.toPlainText().strip().split("\n")
        positive = " ".join(positive)
        negative = self.txt_negative.toPlainText().strip().split("\n")
        negative = " ".join(negative)

        image = QPixmap(self.current_image_path)
        w, h = image.width(), image.height()
        if w > h:
            size_str = "1216x832"
        elif h > w:
            size_str = "832x1216"
        else:
            size_str = "1024x1024"

        if not positive:
            positive = "1boy, 1 man"

        if not negative:
            negative = "(1girl, woman, female)"

        content = f"{positive}###{negative}###{size_str}"
        prompt_path = os.path.splitext(self.current_image_path)[0] + ".txt"

        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(content)

    def handle_dropped_images(self, image_paths):
        if not image_paths:
            return

        # Cập nhật folder_path và label
        folder = os.path.dirname(image_paths[0])
        self.folder_path = folder
        self.lbl_folder.setText(folder)

        # Lưu danh sách ảnh vào thư mục đó (không trùng)
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        all_images = sorted([f for f in os.listdir(folder) if any(f.lower().endswith(ext) for ext in image_extensions)])

        self.list_images.clear()
        metrics = QFontMetrics(self.list_images.font())
        for file in all_images:
            full_path = os.path.join(folder, file)
            icon = QIcon(full_path)
            display_name = metrics.elidedText(file, Qt.ElideMiddle, 140)
            item = QListWidgetItem(icon, display_name)
            item.setData(Qt.UserRole, full_path)
            item.setToolTip(file)
            self.list_images.addItem(item)

        # Hiển thị ảnh đầu tiên trong danh sách kéo vào
        self.list_images.setCurrentRow(0)
        self.display_image_from_path(image_paths[0])
        self.load_prompt_file(image_paths[0])

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_D):
            self.navigate_image(1)
        elif key in (Qt.Key_Left, Qt.Key_A):
            self.navigate_image(-1)

    def navigate_image(self, step):
        current_row = self.list_images.currentRow()
        total = self.list_images.count()
        next_row = (current_row + step) % total
        self.list_images.setCurrentRow(next_row)
        item = self.list_images.item(next_row)
        if item:
            self.display_selected_image(item)

    


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        with open("ElegantDark.qss", "r") as f:
            app.setStyleSheet(f.read())
    except:
        pass
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())