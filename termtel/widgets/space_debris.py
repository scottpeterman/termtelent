from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QApplication, QGraphicsView,
                             QGraphicsScene, QGraphicsItem, QGraphicsSimpleTextItem, QGraphicsDropShadowEffect)
from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QBrush, QColor, QPen
from enum import Enum
from math import sin, cos, radians, pi
import random


class GameState(Enum):
    WAITING = 0
    RUNNING = 1
    PAUSED = 2
    GAME_OVER = 3


class AsteroidsWidget(QWidget):
    # Define signals for external communication
    scoreChanged = pyqtSignal(int)
    livesChanged = pyqtSignal(int)
    levelChanged = pyqtSignal(int)
    gameStateChanged = pyqtSignal(GameState)

    def __init__(self, color=Qt.GlobalColor.white, parent=None):
        super().__init__(parent)

        if "light" not in parent.theme:
            self.game_color = self.ensure_visible_on_black(color)
        else:
            self.game_color = color

        self.parent=parent
        self.initUI()

    def initUI(self):
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create and add game view with color
        self.gameView = GameView(self.game_color)
        layout.addWidget(self.gameView)

        # Connect signals from game view
        self.gameView.scoreChanged.connect(self.scoreChanged)
        self.gameView.livesChanged.connect(self.livesChanged)
        self.gameView.levelChanged.connect(self.levelChanged)
        self.gameView.gameStateChanged.connect(self.gameStateChanged)

    def ensure_visible_on_black(self, color):
        """
        Ensures a color will be visible on a black background by checking its luminance
        and adjusting if necessary.

        Args:
            color: QColor or Qt.GlobalColor to check

        Returns:
            QColor that is guaranteed to be visible on black
        """
        # Convert to QColor if it's a Qt.GlobalColor
        if not isinstance(color, QColor):
            color = QColor(color)

        # Calculate relative luminance using standard coefficients
        luminance = (0.299 * color.red() +
                     0.587 * color.green() +
                     0.114 * color.blue()) / 255.0

        # If luminance is too low (color too dark), adjust it
        MIN_LUMINANCE = 0.4  # Minimum luminance for visibility

        if luminance < MIN_LUMINANCE:
            # Preserve the hue but adjust saturation and value
            h = color.hue()
            s = min(color.saturation(), 200)  # Reduce saturation if very dark
            v = max(color.value(), int(MIN_LUMINANCE * 255))  # Increase brightness

            adjusted_color = QColor()
            adjusted_color.setHsv(h, s, v)
            return adjusted_color

        return color

    def keyPressEvent(self, event):
        self.gameView.keyPressEvent(event)

    def keyReleaseEvent(self, event):
        self.gameView.keyReleaseEvent(event)

    def startGame(self):
        self.gameView.start_game()

    def pauseGame(self):
        if self.gameView.state == GameState.RUNNING:
            self.gameView.state = GameState.PAUSED
            self.gameView.timer.stop()
            self.gameStateChanged.emit(GameState.PAUSED)

    def resumeGame(self):
        if self.gameView.state == GameState.PAUSED:
            self.gameView.state = GameState.RUNNING
            self.gameView.timer.start()
            self.gameStateChanged.emit(GameState.RUNNING)

    def resetGame(self):
        self.gameView.start_game()

    def getScore(self):
        return self.gameView.score

    def getLives(self):
        return self.gameView.lives

    def getLevel(self):
        return self.gameView.level

    def getGameState(self):
        return self.gameView.state

    def setColor(self, color):
        """Update the game color during runtime"""
        if "light" not in self.parent.theme:
            self.game_color = self.ensure_visible_on_black(color)
        else:
            self.game_color = color
        self.gameView.setColor(self.game_color)


class GameView(QGraphicsView):
    # Define signals
    scoreChanged = pyqtSignal(int)
    livesChanged = pyqtSignal(int)
    levelChanged = pyqtSignal(int)
    gameStateChanged = pyqtSignal(GameState)

    def __init__(self, color=Qt.GlobalColor.white):
        super().__init__()
        self.game_color = color
        self.state = GameState.WAITING
        self.initializeGame()

        # Prevent the view from adding any margins
        self.setViewportMargins(0, 0, 0, 0)

        # Ensure the view doesn't apply any transformations
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

    def initializeGame(self):
        # Create scene with dimensions that include space for border
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 800, 600)
        self.setScene(self.scene)

        # Configure view
        self.setBackgroundBrush(QBrush(Qt.GlobalColor.black))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Set view size to match scene size
        self.setFixedSize(800, 600)

        # Ensure viewport matches exactly
        self.setSceneRect(self.scene.sceneRect())

        # Add border with inset to ensure it's fully visible
        border_inset = 2  # Pixels to inset the border
        self.border = self.scene.addRect(
            border_inset,  # Left
            border_inset,  # Top
            800 - (border_inset * 2),  # Width
            600 - (border_inset * 2)  # Height
        )
        self.border.setPen(self.create_glow_pen(self.game_color))
        self.border.setZValue(-1)

        # Rest of initialization
        self.score = 0
        self.lives = 3
        self.level = 1
        self.asteroids = []

        self.createUIElements()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_game)
        self.timer.setInterval(16)

        self.ship = Ship(self.game_color)
        self.scene.addItem(self.ship)
        self.ship.setVisible(False)
        self.ship.setPos(400, 300)

    def create_glow_pen(self, color):
        """Create a pen with a glowing effect"""
        glow_pen = QPen(color, 2)  # Base pen with color

        # Create the glow effect
        effect = QGraphicsDropShadowEffect()
        effect.setColor(color)
        effect.setBlurRadius(15)
        effect.setOffset(0, 0)

        return glow_pen
    def setColor(self, color):
        """Update the game color during runtime"""
        self.game_color = color
        # Update existing elements
        self.score_text.setBrush(QBrush(color))
        self.lives_text.setBrush(QBrush(color))
        if hasattr(self, 'start_text'):
            self.start_text.setBrush(QBrush(color))
        # Update ship and asteroids
        if self.ship:
            self.ship.setColor(color)
        for asteroid in self.asteroids:
            asteroid.setColor(color)

        if hasattr(self, 'border'):
            self.border.setPen(self.create_glow_pen(color))

    def createUIElements(self):
        # Create vector-style text
        self.score_text = QGraphicsSimpleTextItem("00000")
        self.lives_text = QGraphicsSimpleTextItem("SHIPS 3")
        self.score_text.setBrush(QBrush(self.game_color))
        self.lives_text.setBrush(QBrush(self.game_color))
        self.scene.addItem(self.score_text)
        self.scene.addItem(self.lives_text)
        self.score_text.setPos(10, 10)
        self.lives_text.setPos(10, 30)

        # Create start message
        self.start_text = QGraphicsSimpleTextItem("PUSH START")
        self.start_text.setBrush(QBrush(self.game_color))
        font = self.start_text.font()
        font.setPointSize(24)
        self.start_text.setFont(font)
        text_width = self.start_text.boundingRect().width()
        self.start_text.setPos((800 - text_width) / 2, 250)
        self.scene.addItem(self.start_text)

    def update_game(self):
        if self.state != GameState.RUNNING:
            return

        # Update all game objects
        for item in self.scene.items():
            if isinstance(item, (Ship, Asteroid, Bullet)):
                item.advance(1)

        # Handle collisions
        if self.ship and self.ship.isVisible():
            for item in self.scene.collidingItems(self.ship):
                if isinstance(item, Asteroid):
                    self.handle_ship_collision()
                    break

        # Check bullet collisions and update score
        for item in self.scene.items():
            if isinstance(item, Bullet):
                for colliding_item in self.scene.collidingItems(item):
                    if isinstance(colliding_item, Asteroid):
                        self.score += (4 - colliding_item.size) * 100
                        self.score_text.setText(f"{self.score:05d}")
                        self.scoreChanged.emit(self.score)
                        self.handle_asteroid_destruction(colliding_item)
                        self.scene.removeItem(item)
                        break
                # Remove bullets that are out of bounds
                if not self.scene.sceneRect().contains(item.pos()):
                    self.scene.removeItem(item)

        # Check if level is complete
        if not self.asteroids:
            self.start_new_level()

    def handle_ship_collision(self):
        self.lives -= 1
        self.lives_text.setText(f"SHIPS {self.lives}")
        self.livesChanged.emit(self.lives)

        if self.lives <= 0:
            self.game_over()
        else:
            # Make ship temporarily invulnerable
            self.ship.setVisible(False)
            # Reset ship position and movement
            self.ship.setPos(400, 300)
            self.ship.vel = QPointF(0, 0)
            self.ship.angle = 0
            self.ship.setRotation(0)
            self.ship.thrust = False
            self.ship.rotation_speed = 0

            # Use a timer to make the ship reappear after a short delay
            QTimer.singleShot(2000, self.respawn_ship)

    def respawn_ship(self):
        if self.state == GameState.RUNNING:
            self.ship.setVisible(True)

    def handle_asteroid_destruction(self, asteroid):
        self.asteroids.remove(asteroid)
        if asteroid.size > 1:
            # Split into smaller asteroids
            for _ in range(2):
                new_asteroid = Asteroid(
                    position=asteroid.pos(),
                    size=asteroid.size - 1,
                    color=self.game_color
                )
                self.asteroids.append(new_asteroid)
                self.scene.addItem(new_asteroid)
        self.scene.removeItem(asteroid)

    def start_new_level(self):
        self.level += 1
        self.levelChanged.emit(self.level)
        num_asteroids = min(3 + self.level, 11)  # Cap at 11 asteroids

        # Reset ship position
        self.ship.setPos(400, 300)
        self.ship.vel = QPointF(0, 0)
        self.ship.angle = 0
        self.ship.setRotation(0)

        # Create new asteroids away from ship
        for _ in range(num_asteroids):
            while True:
                asteroid = Asteroid(size=3, color=self.game_color)
                # Ensure asteroids spawn away from ship
                if (asteroid.pos() - self.ship.pos()).manhattanLength() > 100:
                    self.asteroids.append(asteroid)
                    self.scene.addItem(asteroid)
                    break

    def start_game(self):
        self.state = GameState.RUNNING
        self.gameStateChanged.emit(self.state)
        self.score = 0
        self.lives = 3
        self.level = 1
        self.score_text.setText("00000")
        self.lives_text.setText("SHIPS 3")

        # Clear ALL existing objects including game over text
        for item in self.scene.items():
            if isinstance(item, (Asteroid, Bullet, QGraphicsSimpleTextItem)):
                # Don't remove score and lives text
                if item not in (self.score_text, self.lives_text):
                    self.scene.removeItem(item)
        self.asteroids.clear()

        # Reset ship completely
        self.ship.setVisible(True)
        self.ship.setPos(400, 300)
        self.ship.vel = QPointF(0, 0)  # Reset velocity
        self.ship.angle = 0
        self.ship.setRotation(0)
        self.ship.thrust = False  # Make sure thrust is off
        self.ship.rotation_speed = 0  # Reset rotation

        # Create initial asteroids
        self.start_new_level()

        # Start the game timer
        self.timer.start()

    def game_over(self):
        self.state = GameState.GAME_OVER
        self.gameStateChanged.emit(self.state)
        self.timer.stop()
        self.ship.setVisible(False)

        # Create vector-style game over text
        game_over_text = QGraphicsSimpleTextItem("GAME OVER")
        game_over_text.setBrush(QBrush(self.game_color))
        font = game_over_text.font()
        font.setPointSize(24)
        game_over_text.setFont(font)

        # Center the text
        text_width = game_over_text.boundingRect().width()
        game_over_text.setPos((800 - text_width) / 2, 250)
        self.scene.addItem(game_over_text)

        # Add "Push Start" message
        restart_text = QGraphicsSimpleTextItem("PUSH START")
        restart_text.setBrush(QBrush(self.game_color))
        restart_text.setFont(font)
        text_width = restart_text.boundingRect().width()
        restart_text.setPos((800 - text_width) / 2, 300)
        self.scene.addItem(restart_text)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            if self.state == GameState.WAITING or self.state == GameState.GAME_OVER:
                self.start_game()
                return
            elif self.state == GameState.RUNNING:
                self.ship.shoot()
                return

        if self.state == GameState.RUNNING:
            if event.key() == Qt.Key.Key_Up:
                self.ship.thrust = True
            elif event.key() == Qt.Key.Key_Left:
                self.ship.rotation_speed = -5
            elif event.key() == Qt.Key.Key_Right:
                self.ship.rotation_speed = 5
            elif event.key() == Qt.Key.Key_P:
                self.state = GameState.PAUSED
                self.gameStateChanged.emit(self.state)
                self.timer.stop()
        elif self.state == GameState.PAUSED:
            if event.key() == Qt.Key.Key_P:
                self.state = GameState.RUNNING
                self.gameStateChanged.emit(self.state)
                self.timer.start()

    def keyReleaseEvent(self, event):
        if self.state == GameState.RUNNING:
            if event.key() == Qt.Key.Key_Up:
                self.ship.thrust = False
            elif event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
                self.ship.rotation_speed = 0

    def advance(self, phase):
        if phase == 0 or self.state != GameState.RUNNING:
            return

        # Update all game objects
        sceneRect = self.scene.sceneRect()

        for item in self.scene.items():
            if isinstance(item, (Ship, Asteroid, Bullet)):
                item.advance(1)

                # Wrap objects at exact scene boundaries
                if isinstance(item, (Ship, Asteroid)):
                    pos = item.pos()
                    x, y = pos.x(), pos.y()

                    if x < 0:
                        x = sceneRect.width()
                    elif x > sceneRect.width():
                        x = 0
                    if y < 0:
                        y = sceneRect.height()
                    elif y > sceneRect.height():
                        y = 0

                    if x != pos.x() or y != pos.y():
                        item.setPos(x, y)

                # Remove bullets that are out of bounds
                elif isinstance(item, Bullet) and not sceneRect.contains(item.pos()):
                    self.scene.removeItem(item)


class Ship(QGraphicsItem):
    def __init__(self, color=Qt.GlobalColor.white):
        super().__init__()
        self.color = color
        self.thrust = False
        self.rotation_speed = 0
        self.vel = QPointF(0, 0)
        self.angle = 0

    def setColor(self, color):
        self.color = color
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-10, -10, 20, 20)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        points = [
            QPointF(0, -10),  # Nose
            QPointF(-7, 10),  # Left corner
            QPointF(0, 7),  # Back center
            QPointF(7, 10),  # Right corner
            QPointF(0, -10),  # Back to nose
        ]

        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])

        if self.thrust:
            thrust_points = [
                QPointF(-3, 8),  # Left
                QPointF(0, 13),  # Center
                QPointF(3, 8),  # Right
            ]
            for i in range(len(thrust_points) - 1):
                painter.drawLine(thrust_points[i], thrust_points[i + 1])

    def advance(self, phase):
        if phase == 0:
            return

        if self.rotation_speed != 0:
            self.angle += self.rotation_speed
            self.setRotation(self.angle)

        if self.thrust:
            angle_rad = radians(self.angle - 90)
            thrust = QPointF(
                cos(angle_rad) * 0.2,
                sin(angle_rad) * 0.2
            )
            self.vel += thrust

        # Apply slight drag
        self.vel *= 0.99

        # Update position
        new_pos = self.pos() + self.vel

        # Wrap around screen edges with exact dimensions
        x = new_pos.x()
        y = new_pos.y()

        # Add a small buffer to ensure complete wrapping
        if x < -10:
            x = 800
        elif x > 810:
            x = 0
        if y < -10:
            y = 600
        elif y > 610:
            y = 0

        self.setPos(x, y)

    def shoot(self):
        angle_rad = radians(self.angle - 90)  # Adjust angle since ship points up
        nose_pos = self.pos() + QPointF(
            cos(angle_rad) * 10,
            sin(angle_rad) * 10
        )
        bullet = Bullet(nose_pos, self.angle - 90, self.color)
        self.scene().addItem(bullet)
        return bullet


class Bullet(QGraphicsItem):
    def __init__(self, position, angle, color=Qt.GlobalColor.white):
        super().__init__()
        self.color = color
        self.setPos(position)
        self.angle = angle
        self.speed = 10

    def setColor(self, color):
        self.color = color
        self.update()

    def boundingRect(self) -> QRectF:
        return QRectF(-1, -1, 2, 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.color, 2))
        painter.drawPoint(0, 0)

    def advance(self, phase):
        if phase == 0:
            return

        angle_rad = radians(self.angle)
        self.setPos(
            self.pos() + QPointF(
                cos(angle_rad) * self.speed,
                sin(angle_rad) * self.speed
            )
        )


class Asteroid(QGraphicsItem):
    def __init__(self, position=None, size=3, color=Qt.GlobalColor.white):
        super().__init__()
        self.color = color
        self.size = size

        # Generate vector-style asteroid shape
        num_points = random.randint(6, 8)  # Fewer points for retro look
        self.points = []

        # Create base shape
        for i in range(num_points):
            angle = (i / num_points) * 2 * pi
            radius = 10 * self.size * (1 + random.uniform(-0.2, 0.2))
            self.points.append(QPointF(
                radius * cos(angle),
                radius * sin(angle)
            ))
        # Close the shape by repeating first point
        self.points.append(self.points[0])

        # Set random position if not specified
        if position:
            self.setPos(position)
        else:
            self.setPos(
                random.randint(0, 800),
                random.randint(0, 600)
            )

        # Movement properties
        speed = random.uniform(0.5, 2.0)
        angle = random.uniform(0, 2 * pi)
        self.vel = QPointF(speed * cos(angle), speed * sin(angle))
        self.rotation_speed = random.uniform(-1, 1)
        self.angle = 0

    def setColor(self, color):
        self.color = color
        self.update()

    def boundingRect(self) -> QRectF:
        size = 12 * self.size
        return QRectF(-size, -size, size * 2, size * 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for i in range(len(self.points) - 1):
            painter.drawLine(self.points[i], self.points[i + 1])

    def advance(self, phase):
        if phase == 0:
            return

        # Update position
        new_pos = self.pos() + self.vel

        # Wrap around screen edges with exact dimensions
        x = new_pos.x()
        y = new_pos.y()

        # Add a small buffer to ensure complete wrapping
        if x < -10:
            x = 800
        elif x > 810:
            x = 0
        if y < -10:
            y = 600
        elif y > 610:
            y = 0

        self.setPos(x, y)

        # Update rotation
        self.angle += self.rotation_speed
        self.setRotation(self.angle)

# Example usage
if __name__ == '__main__':
    import sys

    app = QApplication(sys.argv)

    # Create the widget with a custom color (default is white)
    # asteroidsWidget = AsteroidsWidget(Qt.GlobalColor.cyan)  # For cyan theme
    # asteroidsWidget = AsteroidsWidget(QColor("#00FF00"))   # For green theme
    asteroidsWidget = AsteroidsWidget(QColor("#00FF00"))  # Default white
    asteroidsWidget.show()

    # Example of connecting to signals
    asteroidsWidget.scoreChanged.connect(lambda score: print(f"Score: {score}"))
    asteroidsWidget.gameStateChanged.connect(lambda state: print(f"Game State: {state}"))

    sys.exit(app.exec())