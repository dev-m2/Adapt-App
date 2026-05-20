#import core.main
from textual.app import App
from textual.widgets import Static

class HelloApp(App):
    def compose(self):
        yield Static("Hello World") # something about a generator, yada-yada,??
    
if __name__ == "__main__":
    app = HelloApp()
    app.run()

#core.main.test()