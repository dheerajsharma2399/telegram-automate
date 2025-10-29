# Deploying the Telegram Bot and Web Dashboard to AWS EC2

This guide provides step-by-step instructions for deploying the application to an AWS EC2 instance.

## 1. Provision an EC2 Instance

1.  Launch a new EC2 instance on AWS. A recent version of **Ubuntu Server** is recommended.
2.  When configuring the instance, create a **security group** that allows inbound traffic on the following ports:
    *   **Port 22 (SSH):** To allow you to connect to the instance.
    *   **Port 80 (HTTP):** To allow users to access your web dashboard.
3.  Create and download a **key pair**. You will need this to SSH into your instance.

## 2. Connect to the EC2 Instance

Use SSH to connect to your EC2 instance. Replace `your-key.pem` with the path to your key pair file and `your_ec2_ip` with the public IP address of your instance.

```bash
ssh -i /path/to/your-key.pem ubuntu@your_ec2_ip
```

## 3. Install Dependencies on the EC2 Instance

1.  Update the package manager and install Python, pip, and a virtual environment tool:

    ```bash
    sudo apt-get update
    sudo apt-get install python3-pip python3.10-venv -y
    ```

2.  Install Nginx, which will be used as a reverse proxy:

    ```bash
    sudo apt-get install nginx -y
    ```

## 4. Transfer Application Files

From your **local machine**, use `scp` to transfer your project directory to the EC2 instance.

```bash
scp -i /path/to/your-key.pem -r . ubuntu@your_ec2_ip:/home/ubuntu/telegram-automate
```

## 5. Set Up the Application on the EC2 Instance

1.  **Navigate to the project directory** on your EC2 instance:

    ```bash
    cd /home/ubuntu/telegram-automate
    ```

2.  **Create and activate a Python virtual environment:**

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required Python packages:**

    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:** Create a `.env` file and add the necessary environment variables for your application (e.g., API keys, database credentials).

## 6. Run the Application with `systemd`

We will use `systemd` to manage the web server and Telegram bot as background services.

1.  **Create a `wsgi.py` file:**
    In your project's root directory, create a new file named `wsgi.py` with the following content:

    ```python
    from web_server import app

    if __name__ == "__main__":
        app.run()
    ```

2.  **Create the `systemd` Service File for the Web Server:**
    Create a file named `job-dashboard.service` with the following content.

    **Important:** You may need to adjust the `User` and the paths in `WorkingDirectory` and `ExecStart` to match your specific setup on the EC2 instance.

    ```ini
    [Unit]
    Description=Job Dashboard Web Server
    After=network.target

    [Service]
    User=ubuntu
    Group=www-data
    WorkingDirectory=/home/ubuntu/telegram-automate
    ExecStart=/home/ubuntu/telegram-automate/venv/bin/gunicorn --workers 3 --bind unix:job-dashboard.sock -m 007 wsgi:app
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

3.  **Create the `systemd` Service File for the Telegram Bot:**
    Create a file named `telegram-job-bot.service` with the following content.

    **Important:** As with the previous file, you may need to adjust the `User` and the paths to match your setup.

    ```ini
    [Unit]
    Description=Telegram Job Bot
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/telegram-automate
    ExecStart=/home/ubuntu/telegram-automate/venv/bin/python main.py
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

4.  **Deploy and Start the Services:**
    a.  Move the service files to the `systemd` directory:
        ```bash
        sudo mv job-dashboard.service /etc/systemd/system/
        sudo mv telegram-job-bot.service /etc/systemd/system/
        ```
    b.  Reload the `systemd` daemon:
        ```bash
        sudo systemctl daemon-reload
        ```
    c.  Start your services:
        ```bash
        sudo systemctl start job-dashboard.service
        sudo systemctl start telegram-job-bot.service
        ```
    d.  Enable the services to start on boot:
        ```bash
        sudo systemctl enable job-dashboard.service
        sudo systemctl enable telegram-job-bot.service
        ```

## 7. Configure Nginx as a Reverse Proxy

1.  **Create an Nginx Configuration File:**
    Create a new Nginx configuration file at `/etc/nginx/sites-available/job-dashboard` with the following content.

    **Important:** Replace `your_domain_or_IP` with your EC2 instance's public IP address or your domain name.

    ```nginx
    server {
        listen 80;
        server_name your_domain_or_IP;

        location / {
            include proxy_params;
            proxy_pass http://unix:/home/ubuntu/telegram-automate/job-dashboard.sock;
        }
    }
    ```

2.  **Enable the New Site Configuration:**
    Create a symbolic link to enable the site:

    ```bash
    sudo ln -s /etc/nginx/sites-available/job-dashboard /etc/nginx/sites-enabled
    ```

3.  **Test and Restart Nginx:**
    a.  Test your Nginx configuration:
        ```bash
        sudo nginx -t
        ```
    b.  Restart Nginx to apply the changes:
        ```bash
        sudo systemctl restart nginx
        ```

Your application should now be deployed and accessible.
