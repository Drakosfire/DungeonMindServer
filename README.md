# DungeonMind - TTRPG Support Platform

DungeonMind is a platform designed to support tabletop role-playing game (TTRPG) players, game masters, and content creators. This repository contains the modular FastAPI application that provides backend capabilities within the larger multi-container DungeonMind product.

## Project Overview

DungeonMind combines a FastAPI backend application with separate product containers and infrastructure. Within this server, the Rules-As-Guide system, card generator, statblock tools, and store features are modular routes and packages—not independently deployed backend microservices.

## Key Features

- **Professional Landing Page**: A separate React product container introduces the DungeonMind platform and its tools.
- **API Server**: Built with FastAPI, the API server handles backend logic and supports all the TTRPG tools with a RESTful architecture.
- **StoreGenerator Module**: Backend routes and packages for creating and managing in-game shops and stores.
- **AI-Enhanced Tools**:
   - **Rules Lawyer**: An interactive Rules-As-Guide (RAG) system that provides in-context rule guidance for smoother gameplay.
   - **Card Generator**: Customizable TTRPG cards for characters, items, or spells, enhancing game immersion.
   - **Statblock Generator**: Automatic generation of stat blocks for characters and creatures, simplifying preparation for game masters.
- **NGINX and Cloudflare Configuration**: Efficient routing and redirection management to ensure secure, reliable, and fast access to all microservices.

## Project Goals

DungeonMind serves as a showcase for a modular, scalable TTRPG support platform, with the following goals:

1. **Demonstrate Advanced Development Skills**: Showcase Alan Meigs' ability to create a modern, microservices-based web application utilizing Docker, NGINX, FastAPI, and React.
2. **Enhance TTRPG Gameplay with AI and Automation**: Provide interactive, AI-driven tools that accelerate TTRPG world-building and make running campaigns smoother and more accessible.
3. **Provide a Robust, Scalable Demo Platform**: Create a flexible and scalable foundation to support further tool development and feature additions, with potential for future user expansion.

## Architecture

DungeonMind is deployed as a multi-container product. This repository is one modular FastAPI application within that product:

- **Hostinger**: Domain and VPS.
- **Frontend Service**: Hosts the React-based landing page, showcasing the platform and handling user interactions.
- **DungeonMindAPI Server**: Manages backend logic, data processing, and serves the central API through modular routers and packages.
- **StoreGenerator Module**: A feature module within the API server, not an independently deployed backend service.
- **Reverse Proxy and Security**: NGINX handles routing and load balancing between services, while Cloudflare provides additional security, caching, and SSL/TLS support.
- **Cloudflare**: Providing caching, security, and DNS services.

## Deployment

DungeonMind uses Docker for the product's containers. NGINX routes requests between product containers, while Cloudflare provides DNS, TLS, caching, and security services. This FastAPI application is deployed as one backend container; modular feature packages can be extracted only when a real deployment need justifies it.

## Future Plans

DungeonMind is an evolving project with plans to expand tool functionality, enhance generative AI integration, and support even more complex TTRPG systems. Planned features include enhanced user interfaces, expanded API endpoints, and a broader range of AI-driven TTRPG creation tools.

