This is a brand new repo, I'd like to work on creating the following:

An python based asset management system that works using only the filesystem. It's main usecase is to allow for a small studio to manage assets created from gen ai workflows. In this system, we want to publish text, images, videos, and any type of files as reusable, versionable, and tagable assets.  The core workflow is:

Create a project: The project name is then a root folder that can exist where the user likes. All assets will be versioned within that root project. 
Create an asset schema. This by default is project/tree/asset/variant/subVariant. "project" is a facet, "tree" is a facet, etc. So an example asset might be: /myProject/assets/simpleBox/base/default. Then each time a file is published to this asset. it is allocated a version. So it's relative path from the project root would be: 

myProject/assets/simpleBox/base/default/v001/simpleBox.txt 

Then whenever the user publishes another file to this path, the new version is allocated by checking the latest current version, and incrementing. so:
myProject/assets/simpleBox/base/default/v002/simpleBox.txt

In this system, there is only one file per asset. The goal is to provide a simple, versionable, file management system. We then have a straight forward api that allows users to publish, retreive, and query for assets, facets, all the basic needs for this system to be used in a simple but powerful versioning system.

Another part os this system is the ability to tag versions. For some tags, like the "ready" tag, they can only be applied to a single version of an asset. Meaning if you tag a new version, the tag is removed from the previous version that contained that tag. Other tags can be on multiple versions of an asset.

For a tag that can be on multiple versions. we store it within the version folder as a simple text document with a .gtst extension:
myProject/assets/simpleBox/base/default/v001/simpleBox.txt 
myProject/assets/simpleBox/base/default/v001/someTag.gtst

But for a tag which only is allowed on one version of an item, we store it before the version folder in a folder of its own. We date these tags so we don't overwrite any files when updating a tag to a new version. Then when getting the value of the tag for the version, we look at the latest defined tag.
myProject/assets/simpleBox/base/default/v001/simpleBox.txt 
myProject/assets/simpleBox/base/default/gtst_tags/ready_001.gtst

The suffix is incremented everytime a new tag is added. The contents of the text file shows what version of the asset is tagged. and it uses a simple version path:
myProject/assets/simpleBox/base/default/v001
This is to prevent referencing the filename itself as that can be changed.