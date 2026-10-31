# Heads-Up
CIS 2999 course project repository. This repository is for our implementation of a reminder app called Heads Up.

---

## How to run it

### 1. Clone the Repository
Open your terminal and run:

```bash
git clone https://github.com/AxelD7/heads-up.git
cd heads-up
```

### 2. Create and Source your virtual environment
A virtual environment (venv) creates an isolated Python environment specifically for this project. It keeps the project's dependencies separate from other Python projects on your machine and helps ensure everyone is using the correct packages without conflicts.

To create venv file inside heads-up repo run:
``` bash
python3 -m venv venv
```
To activate/source your venv 
Linux / macOS:
``` bash
source venv/bin/activate
```

Windows (Command Prompt):

```cmd
venv\Scripts\activate
```
### 3. Install dependencies
When your venv is active run:
```bash
pip install -r requirements.txt
```

### 4. Start the Development Server

```bash
python manage.py runserver
```

Once the server is running, open your browser and navigate to:

http://127.0.0.1:8000/users/

You should now be able to view the "Hello world from Users App" locally.

## Project Structure Example

It should be known that django defines "features" or "domains" as apps. So in our projects things such as `events`, `users` or `notifications` will more than likely become their own apps within our project. They are still apart of the same site but allow for us have a few benefits long term.

### Why Use Multiple Django Apps?
- Reusability: Features like authentication can be packaged and dropped into future projects without rewriting code.
- Separation of Concerns: Isolating features into modules stops code bloat and keeps the system easy to navigate.
- Simpler Testing & Scaling: Smaller apps make unit testing straightforward and allow team members to build and debug components independently- 
- Future-Proofing: Distinct app boundaries make it much easier to break features out into microservices later if your project grows

To create a new app, in the project root: 
``` bash
python manage.py startapp myotherapp
```
where `myotherapp` is the name of the app you are creating.

- **config/** - Global project settings and project wide URL routing.
- **users/** - Handles user account and login views.
  - **migrations/** - Contains database migrations for this specific folder.
  - `models.py` - User database model.
  - `views.py` - User logic and test views.
  - `urls.py` - URL paths for user pages.
- **myotherfeature/**
  - `models.py` - other database model.
  - `...`
- **manage.py** - Main command-line tool to run the server and migrations.
- **requirements.txt** - Python packages needed to run the project.
- **.gitignore** - Tells Git to skip `venv` and `db.sqlite3`.

## Contributing 
To keep our repository clean and avoid code conflicts, follow this workflow for every new feature or bug fix:

### 1. Pick or Create an Issue:
  Find the issue you're working on on our GitHub issue board (or create one if it doesn't exist yet).

### 2. Create a New Branch:
  Always pull the latest changes from `main` before creating your branch:
   ```bash
   git checkout main
   git pull origin main
   git checkout -b feature/short-description
   ```
(e.g., feature/user-auth or fix/login-error)

### 3. Make and Commit Your Changes:
  Keep commits focused and write clear commit messages:
  
  ```bash
  git add .
  git commit -m "Add basic user login view"

  ```

### 4. Push Your Branch & Open a Pull Request (PR):
After commiting your changes, you need to push your branch if you have not done so already.
  ```bash
  git push origin feature/short-description
  ```

  Go to GitHub, open a Pull Request against the main branch, tag the team members for review, and link the issue you worked on. Please include a brief summary of what you built or fixed.


## Resources
- [Official Django Tutorial](https://docs.djangoproject.com/en/6.1/intro/tutorial01/)
- [W3Schools Django Tutorial](https://www.w3schools.com/django/django_intro.php)
  (Side bar should have table of contents)