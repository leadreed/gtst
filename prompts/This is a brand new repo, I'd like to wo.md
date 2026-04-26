This is a brand new repo, I'd like to work on creating the following:

An python based asset management system that works using only the filesystem. It's main usecase is to allow for a small studio to manage assets created from gen ai workflows. In this system, we want to publish text, images, videos, and any type of files as reusable, versionable, and tagable assets.  The core workflow is:

Create a project: The project name is then a root folder that can exist where the user likes. All assets will be versioned within that root project. 
Create an asset schema. This by default is project/tree/asset/variant/subVariant. "project" is a facet, "tree" is a facet, etc. So an example asset might be: /myProject/assets/simpleBox/base/default. Then each time a file is published to this asset. it is allocated a version. So it's relative path from the project root would be: 

myProject/assets/simpleBox/base/default/v001/simpleBox.txt 

Then whenever the user publishes another file to this path, the new version is allocated by checking the latest current version, and incrementing. so:
myProject/assets/simpleBox/base/default/v002/simpleBox.txt

In this system, there is only one file per asset. The goal is to provide a simple, versionable, file management system. We then have a straight forward api that allows users to publish, retreive, and query for assets, facets, all the basic needs for this system to be used in a simple but powerful versioning system.

