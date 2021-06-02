#
# Copyright (c) 2021 Wind River Systems, Inc.
#
# SPDX-License-Identifier: Apache-2.0
#
# All Rights Reserved.
#

from tests import rbac_test_base

class TestImages(rbac_test_base.TestClass):

    # ---------------------------------------------------------------------
    # TC-1
    # Description:
    # - user11 as project_admin of project1, can create/list/detail/modify/
    #   delete/upload/download images of project1
    # - user11 can deactivate/reactivate images of project1
    # - user13 can get list/detail of images of project1
    # ---------------------------------------------------------------------

    def test_uc_image_1(self):
        """
        1. user11 can create/delete an image
        2. user11 can upload an image file
        3. user11 can detail the image
        4. user11 can deactivate the image of project1
        5. user11 can NOT download the deactivate image
        6. user11 active the image
        7. user11 can download the image
        8. user12/user13 can list the images of project1"
        """

        print("TC-1.1")
        # 1.1. user11 can create/delete an image
        self.set_connections_for_user(self.user11)
        image1 = self._create_image("image1")
        self.assertIn(image1.name,
                      [image.name for image in self._list_images()])
        # print(image1.status)
        self.assertEqual(image1.status, "queued")

        self._delete_image(image1)
        self.assertNotIn("image1",
                         [image.name for image in self._list_images()])

        print("TC-1.2")
        # 1.2. user11 can upload an image file
        image_project1 = self._create_image(
            "image-project1",
            filename="cirros-0.3.4-x86_64-disk.img"
        )
        self.assertIn(
            image_project1.name,
            [image.name for image in self._list_images()]
        )

        print("TC-1.3")
        # 1.3. user11 can detail the image
        image_project1_details = self._get_image_by_id(image_project1.id)
        self.assertEqual(image_project1.name, image_project1_details.name)
        # print(image_project1_details.status)
        self.assertEqual(image_project1_details.status, "active")

        print("TC-1.4")
        # 1.4. user11 can deactivate the image of project1
        self._deactivate_image(image_project1)
        image_project1 = self._get_image_by_id(image_project1.id)
        # print(image_project1.status)
        self.assertEqual(image_project1.status, "deactivated")

        print("TC-1.5")
        # 1.5. user11 can NOT download the deactivate image
        download_response = self._download_image(image_project1)
        self.assertEqual(download_response.status_code, 403)  #HTTP 403 Forbidden
        self.assertIn("The requested image has been deactivated. Image data download is forbidden.", download_response.text)

        print("TC-1.6")
        # 1.6. user11 active the image
        self._reactivate_image(image_project1)
        image_project1 = self._get_image_by_id(image_project1.id)
        self.assertEqual(image_project1.status, "active")

        print("TC-1.7")
        # 1.7. user11 can download the image
        self.assertEqual(self._download_image(image_project1).status_code, 200)

        print("TC-1.8")
        # 1.8. user12/user13 can list the images of project1"
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertIn(image_project1.name,
                          [image.name for image in self._list_images()])

    # ---------------------------------------------------------------------
    # TC-2
    # Description:
    # - user12, as member of project1, can create/modify/upload images of
    #   project1
    # - user12 can NOT delete/deactivate/reactivate images of project1
    # ---------------------------------------------------------------------

    def test_uc_image_2(self):
        """
        1. user12 can create/modify an image
        2. user12 can upload an image file
        3. user12 can detail the image
        4. user12 can download the image
        5. user12 can NOT delete the image
        6. user12 can NOT deactivate/reactivate the image of project1
        """

        # For the following test items under this test case
        self.set_connections_for_user(self.user12)

        # ---------------------------------------------------------------------
        # 2.1. user12 can create/modify an image of project1
        # ---------------------------------------------------------------------
        print("TC-2.1")

        # Create
        self.set_connections_for_user(self.user12)
        image2 = self._create_image("image2")
        self.assertIn("image2", [image.name for image in self._list_images()])
        # print(image2.status)
        self.assertEqual(image2.status, "queued")

        # Modify (update)
        image2 = self._update_image(image2, name="image2-project1")
        self.assertEqual(image2.name, "image2-project1")
        self.assertIn(
            "image2-project1",
            [image.name for image in self._list_images()]
        )
        self.assertNotIn(
            "image2",
            [image.name for image in self._list_images()]
        )

        # ---------------------------------------------------------------------
        # 2.2. user12 can upload an image file
        # ---------------------------------------------------------------------

        print("TC-2.2")

        # Upload
        self._upload_image(image2.id, "cirros-0.3.4-x86_64-disk.img")
        image2 = self._get_image_by_id(image2.id)
        # print(image2.status)
        self.assertEqual(image2.status, "active")

        # ---------------------------------------------------------------------
        # 2.3. user12 can detail the image
        # ---------------------------------------------------------------------

        print("TC-2.3")

        # Detail (get)
        image2 = self._get_image_by_id(image2.id)
        self.assertEqual(image2.name, "image2-project1")

        # ---------------------------------------------------------------------
        # 2.4. user12 can download the image
        # ---------------------------------------------------------------------

        print("TC-2.4")

        # Download
        download_response = self._download_image(image2)
        # print(download_response)
        self.assertEqual(download_response.status_code, 200)  # HTTP 200 OK

        # ---------------------------------------------------------------------
        # 2.5. user12 can NOT delete the image
        # ---------------------------------------------------------------------

        print("TC-2.5")

        # Delete attempt fails
        self.assertRaisesRegex(
            Exception,
            "You are not authorized to complete delete_image action.",
            self._delete_image, image2
        )
        self.assertIn("image2-project1", [image.name for image in self._list_images()])

        # ---------------------------------------------------------------------
        # 2.6. user12 can NOT deactivate/reactivate the image of project1
        # ---------------------------------------------------------------------

        print("TC-2.6")

        print("TC-2.6.1")
        # Deactivate attempt fails for a project member
        self._deactivate_image(image2)
        image2 = self._get_image_by_id(image2.id)
        # print(image2.status)
        self.assertEqual(image2.status, "active")

        print("TC-2.6.2")
        # Deactivate action succeeds for the project admin
        self.set_connections_for_user(self.user11)
        self._deactivate_image(image2)
        image2 = self._get_image_by_id(image2.id)
        # print(image2.status)
        self.assertEqual(image2.status, "deactivated")

        print("TC-2.6.3")
        # Reactivate attempt fails for a project member
        self.set_connections_for_user(self.user12)
        self._reactivate_image(image2)
        image2 = self._get_image_by_id(image2.id)
        # print(image2.status)
        self.assertEqual(image2.status, "deactivated")

        print("TC-2.6.4")
        # Reactivate action succeeds for the project admin
        self.set_connections_for_user(self.user11)
        self._reactivate_image(image2)
        image2 = self._get_image_by_id(image2.id)
        # print(image2.status)
        self.assertEqual(image2.status, "active")

    # ---------------------------------------------------------------------
    # TC-3
    # Description:
    # user11/12/13 as member of project1, can list/detail/download images
    # of project1 and public image of project2, not private image of
    # project2
    # ---------------------------------------------------------------------
    def test_uc_image_3(self):
        """
        1. user21 create a public image in project2
        2. user11/user12/user13 can list/detail/download the public image of project2
        3. user21 create a private image in project2
        4. user11/user12/user13 can NOT find the private image of project2
        """

        # ---------------------------------------------------------------------
        # 3.1. user21 create a public image in project2
        # ---------------------------------------------------------------------

        print("TC-3.1")

        self.set_connections_for_user(self.user21)
        image20 = self._create_image("image-project2-public",
                                     filename="cirros-0.3.4-x86_64-disk.img",
                                     visibility="public")
        self.assertIn("image-project2-public",
                      [image.name for image in self._list_images()])
        image20 = self._get_image_by_id(image20.id)
        # print(image20.status)
        self.assertEqual(image20.status, "active")

        # ---------------------------------------------------------------------
        # 3.2. user11/user12/user13 can list/detail/download the public image
        #      of project2
        # ---------------------------------------------------------------------

        print("TC-3.2")

        for user in (self.user11, self.user12, self.user13):
            self.set_connections_for_user(user)

            # List
            self.assertIn(
                "image-project2-public",
                [image.name for image in self._list_images()]
            )

            # Detail
            image = self._get_image_by_id(image20.id)
            self.assertEqual(image.name, "image-project2-public")

            # Download
            download_response = self._download_image(image20)
            # print(download_response.status_code)
            self.assertEqual(download_response.status_code, 200)  # HTTP 200 OK

        # ---------------------------------------------------------------------
        # 3.3. user21 create a private image in project2
        # ---------------------------------------------------------------------

        print("TC-3.3")

        self.set_connections_for_user(self.user21)
        image21 = self._create_image("image-project2-private",
                                     filename="cirros-0.3.4-x86_64-disk.img",
                                     visibility="private")
        self.assertIn("image-project2-private",
                      [image.name for image in self._list_images()])
        image21 = self._get_image_by_id(image21.id)
        # print(image21.status)
        self.assertEqual(image21.status, "active")

        # ---------------------------------------------------------------------
        # 3.4. user11/user12/user13 can NOT find the private image of project2
        # ---------------------------------------------------------------------

        print("TC-3.4")

        # Users of project 1 can NOT find the image
        for user in (self.user11, self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertNotIn("image-project2-private",
                             [image.name for image in self._list_images()])

        # Users of project 2 can find the image
        for user in (self.user21, self.user22, self.user23):
            self.set_connections_for_user(user)
            self.assertIn("image-project2-private",
                          [image.name for image in self._list_images()])

        # ---------------------------------------------------------------------
        # 3.5. Project 1 members can NOT delete/modify/deactivate/reactivate
        # image of project 2
        # ---------------------------------------------------------------------

        print("TC-3.5")

        print("TC-3.5.1")
        # Delete attempt fails for another project's members
        for user in (self.user11, self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "You are not permitted to delete this image",
                self._delete_image, image20
            )
            self.assertIn("image-project2-public", [image.name for image in self._list_images()])

        print("TC-3.5.2")
        # Modify (update) attempt fails for another project's members
        for user in (self.user11, self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "Forbidden",
                self._update_image, image20,
                name="image-project2-public-newname"
            )
            self.assertNotIn("image-project2-public-newname", [image.name for image in self._list_images()])
            self.assertIn("image-project2-public", [image.name for image in self._list_images()])

        print("TC-3.5.3")
        # Deactivate attempt fails for another project's admin
        self.set_connections_for_user(self.user11)
        self._deactivate_image(image20)
        image20 = self._get_image_by_id(image20.id)
        # print(image20.status)
        self.assertEqual(image20.status, "active")

        print("TC-3.5.4")
        # Deactivate job succeeds for the admin of project 2
        self.set_connections_for_user(self.user21)
        self._deactivate_image(image20)
        image20 = self._get_image_by_id(image20.id)
        # print(image20.status)
        self.assertEqual(image20.status, "deactivated")

        print("TC-3.5.5")
        # Reactivate attempt fails for another project's admin
        self.set_connections_for_user(self.user11)
        self._reactivate_image(image20)
        image20 = self._get_image_by_id(image20.id)
        # print(image20.status)
        self.assertEqual(image20.status, "deactivated")

        print("TC-3.5.6")
        # Reactivate job succeeds for the admin of project 2
        self.set_connections_for_user(self.user21)
        self._reactivate_image(image20)
        image20 = self._get_image_by_id(image20.id)
        # print(image20.status)
        self.assertEqual(image20.status, "active")

    # ---------------------------------------------------------------------
    # TC-4
    # Description:
    # User 11 can publicize a image of project1, while users 12 and 13
    # cannot
    # ---------------------------------------------------------------------
    def test_uc_image_4(self):
        """
        1. user11 tries to create/update a image 'image11' with
            'visibility: public', should succeed,
        2. user12/13 tries to create/update a image 'image12' with
            'visibility: public', should fail,"
        """

        # ---------------------------------------------------------------------
        # 4.1. user11 tries to create/update a image 'image11' with
        # 'visibility: public' should succeed
        # ---------------------------------------------------------------------

        print("TC-4.1")

        self.set_connections_for_user(self.user11)

        # Create image to publicize it
        image11 = self._create_image("image11P", filename="cirros-0.3.4-x86_64-disk.img", visibility="public")
        self.assertIn("image11P", [image.name for image in self._list_images()])
        image11 = self._get_image_by_id(image11.id)
        # print(image11.status)
        self.assertEqual(image11.status, "active")

        # Modify (update) image to publicize it
        shared_image_11 = self._create_image("shared-image-11", filename="cirros-0.3.4-x86_64-disk.img", visibility="shared")
        public_image = self._update_image(shared_image_11, name="public-image", visibility="public")
        self.assertEqual(public_image.name, "public-image")
        self.assertEqual(public_image.visibility, "public")
        self.assertIn("public-image", [image.name for image in self._list_images()])
        self.assertNotIn("shared-image-11", [image.name for image in self._list_images()])

        # ---------------------------------------------------------------------
        # 4.2. user12/13 attempt to create/update an image 'image12' to
        # publicize image should fail
        # ---------------------------------------------------------------------

        print("TC-4.2")

        # Create attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "You are not authorized to complete publicize_image action",
                self._create_image, "image12P", filename="cirros-0.3.4-x86_64-disk.img", visibility="public"
            )
            self.assertNotIn("image12P", [image.name for image in self._list_images()])

        # Modify (update) attempt fails for project members
        self.set_connections_for_user(self.user12)
        shared_image_12 = self._create_image("shared-image-12", filename="cirros-0.3.4-x86_64-disk.img", visibility="shared")
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "Forbidden",
                self._update_image, shared_image_12, name="public-image-12", visibility="public"
            )
            self.assertIn("shared-image-12", [image.name for image in self._list_images()])
            self.assertNotIn("public-image-12", [image.name for image in self._list_images()])

    # ---------------------------------------------------------------------
    # TC-5
    # Description:
    # User 11 can communitize a image of project1, while users 12 and 13
    # cannot
    # ---------------------------------------------------------------------

    def test_uc_image_5(self):
        """
        1. user11 create/update a image 'image11' with 'visibility: community'
        2. user12/13 tries to create/update a image 'image12' with 'visibility: community', should fail
        """

        # ---------------------------------------------------------------------
        # 5.1. user11 can create/update a image 'image11' with
        # 'visibility: community'
        # ---------------------------------------------------------------------

        print("TC-5.1")

        self.set_connections_for_user(self.user11)

        # Create image to communitize it
        image11 = self._create_image("image11C", filename="cirros-0.3.4-x86_64-disk.img", visibility="community")
        self.assertIn("image11C", [image.name for image in self._list_images()])
        image11 = self._get_image_by_id(image11.id)
        # print(image11.status)
        self.assertEqual(image11.status, "active")

        # Modify (update) image to communitize it
        shared_image_11 = self._create_image("shared-image-11", filename="cirros-0.3.4-x86_64-disk.img", visibility="shared")
        community_image = self._update_image(shared_image_11, name="community-image", visibility="community")
        self.assertEqual(community_image.name, "community-image")
        self.assertEqual(community_image.visibility, "community")
        self.assertIn("community-image", [image.name for image in self._list_images()])
        self.assertNotIn("shared-image-11", [image.name for image in self._list_images()])

        # ---------------------------------------------------------------------
        # 5.2. user12/13 attempt to create/update an image 'image12' to
        # communitize the image should fail
        # ---------------------------------------------------------------------

        print("TC-5.2")

        # Create attempt fails for project members
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "You are not authorized to complete communitize_image action",
                self._create_image, "image12C",
                filename="cirros-0.3.4-x86_64-disk.img", visibility="community"
            )
            self.assertNotIn("image12C", [image.name for image in self._list_images()])

        # Modify (update) attempt fails for project members
        self.set_connections_for_user(self.user12)
        shared_image_12 = self._create_image("shared-image-12", filename="cirros-0.3.4-x86_64-disk.img", visibility="shared")
        for user in (self.user12, self.user13):
            self.set_connections_for_user(user)
            self.assertRaisesRegex(
                Exception,
                "Forbidden",
                self._update_image, shared_image_12, name="community-image-12", visibility="community"
            )
            self.assertIn("shared-image-12", [image.name for image in self._list_images()])
            self.assertNotIn("community-image-12", [image.name for image in self._list_images()])