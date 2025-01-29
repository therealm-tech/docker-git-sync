# git-sync Docker image

Image to pull regularly changes on git repository.

By default, the repository is cloned in /home/git/repo.

## Build

```bash
docker build -t git-sync .
```

## Run

```bash
docker run -v ./data:/home/git/repo ghcr.io/therealm-tech/git-sync https://github.com/myorg/myrepo
```

## Configuration

You can run the following command to get all available options.
```bash
docker run ghcr.io/therealm-tech/git-sync --help
```
